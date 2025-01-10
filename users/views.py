import json
import os

import dotenv
from asgiref.sync import sync_to_async
from django.contrib import messages
from django.contrib.auth import aget_user
from django.contrib.auth import alogin as auth_login
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)
from django.shortcuts import redirect, render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from usos_api import USOSClient

from quizzes.models import QuizProgress
from users.models import StudyGroup, Term, User, UserSettings
from users.serializers import UserSerializer

dotenv.load_dotenv()

request_token_secrets = {}


async def login_usos(request):
    confirm_user = request.GET.get("confirm_user", "false") == "true"
    jwt = request.GET.get("jwt", "false") == "true"
    redirect_url = request.GET.get("redirect", "")

    if jwt and not redirect_url:
        return HttpResponseForbidden("Redirect URL must be provided when using JWT")

    callback_url = request.build_absolute_uri(
        f"/authorize/?jwt={str(jwt).lower()}{f'&redirect={redirect_url}' if redirect_url else ''}"
    )

    async with USOSClient(
        "https://apps.usos.pwr.edu.pl/",
        os.getenv("USOS_CONSUMER_KEY"),
        os.getenv("USOS_CONSUMER_SECRET"),
        trust_env=True,
    ) as client:
        client.set_scopes(["offline_access", "studies", "email", "photo", "grades"])
        authorization_url = await client.get_authorization_url(
            callback_url, confirm_user
        )
        request_token, request_token_secret = (
            client.connection.auth_manager.get_request_token()
        )
        request_token_secrets[request_token] = request_token_secret

    return redirect(authorization_url)


async def login_view(request):
    return render(request, "users/login.html")


def admin_login(request):
    next_url = request.GET.get("next", "/admin")
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect(next_url)
    return render(
        request, "users/admin_login.html", {"next": next_url, "username": request.user}
    )


async def authorize(request):
    redirect_url = request.GET.get("redirect", "index")

    async with USOSClient(
        "https://apps.usos.pwr.edu.pl/",
        os.getenv("USOS_CONSUMER_KEY"),
        os.getenv("USOS_CONSUMER_SECRET"),
        trust_env=True,
    ) as client:
        verifier = request.GET.get("oauth_verifier")
        request_token = request.GET.get("oauth_token")
        request_token_secret = request_token_secrets.pop(request_token, None)

        if not request_token_secret:
            return HttpResponseForbidden()

        access_token, access_token_secret = await client.authorize(
            verifier, request_token, request_token_secret
        )
        user = await update_user_data_from_usos(
            client, access_token, access_token_secret
        )

    if request.GET.get("jwt", "false") == "true":
        refresh = await sync_to_async(RefreshToken.for_user)(user)
        return redirect(
            f"{redirect_url}?access_token={refresh.access_token}&refresh_token={refresh}"
        )

    await auth_login(request, user)
    return redirect(redirect_url)


def profile(request):
    return render(request, "users/profile.html", {"user": request.user})


async def update_user_data_from_usos(
    client=None, access_token=None, access_token_secret=None
):
    if not client:
        if not access_token or not access_token_secret:
            raise ValueError(
                "Either client or access_token and access_token_secret must be provided"
            )
        async with USOSClient(
            "https://apps.usos.pwr.edu.pl/",
            os.getenv("USOS_CONSUMER_KEY"),
            os.getenv("USOS_CONSUMER_SECRET"),
            trust_env=True,
        ) as client:
            client.load_access_token(access_token, access_token_secret)
            user_data = await client.user_service.get_user()
    else:
        user_data = await client.user_service.get_user()

    defaults = {
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "email": user_data.email,
        "student_number": user_data.student_number,
        "sex": user_data.sex.value,
        "student_status": user_data.student_status.value,
        "staff_status": user_data.staff_status.value,
        "photo_url": user_data.photo_urls.get(
            "original",
            user_data.photo_urls.get(
                "200x200", next(iter(user_data.photo_urls.values()), None)
            ),
        ),
    }

    if access_token and access_token_secret:
        defaults["access_token"] = access_token
        defaults["access_token_secret"] = access_token_secret

    user_obj, created = await User.objects.aupdate_or_create(
        id=user_data.id, defaults=defaults
    )

    if created:
        user_obj.set_unusable_password()
        await user_obj.asave()

    user_groups = await client.group_service.get_groups_for_user(
        fields=[
            "course_unit_id",
            "group_number",
            "course_name",
            "term_id",
            "class_type",
        ]
    )

    for group in user_groups:
        term, _ = await Term.objects.aget_or_create(
            id=group.term_id,
        )
        group_obj, _ = await StudyGroup.objects.aupdate_or_create(
            id=f"{group.course_unit_id}-{group.group_number}",
            defaults={
                "name": f"{group.course_name.pl} - {group.class_type.pl}, grupa {group.group_number}",
                "term": term,
            },
        )
        await user_obj.study_groups.aadd(group_obj)

    return user_obj


def index(request):
    if not request.user.is_authenticated:
        return render(request, "dashboard.html")
    last_used_quizzes = [
        qp.quiz
        for qp in QuizProgress.objects.filter(user=request.user).order_by(
            "-last_activity"
        )[:4]
    ]
    return render(request, "dashboard.html", {"last_used_quizzes": last_used_quizzes})


@api_view(["GET", "PUT"])
def api_settings(request):
    if request.method == "GET":
        return get_user_settings(request)
    elif request.method == "PUT":
        return update_user_settings(request)
    else:
        return Response(status=HttpResponseNotAllowed.status_code)


def get_user_settings(request):
    if not request.user.is_authenticated:
        return Response(status=HttpResponseForbidden.status_code)

    try:
        user_settings = request.user.settings
    except UserSettings.DoesNotExist:
        user_settings = UserSettings(user=request.user)

    settings_data = {
        "sync_progress": user_settings.sync_progress,
        "initial_repetitions": user_settings.initial_repetitions,
        "wrong_answer_repetitions": user_settings.wrong_answer_repetitions,
    }

    return Response(settings_data)


def update_user_settings(request):
    if not request.user.is_authenticated:
        return Response(status=HttpResponseForbidden.status_code)

    data = json.loads(request.body)

    try:
        user_settings = request.user.settings
    except UserSettings.DoesNotExist:
        user_settings = UserSettings(user=request.user)

    sync_progress = data.get("sync_progress")
    initial_repetitions = data.get("initial_repetitions")
    wrong_answer_repetitions = data.get("wrong_answer_repetitions")

    if sync_progress is not None:
        user_settings.sync_progress = sync_progress

    if initial_repetitions is not None:
        if initial_repetitions >= 1:
            user_settings.initial_repetitions = initial_repetitions
        else:
            return Response(
                "Initial repetitions must be greater or equal to 1",
                status=HttpResponseBadRequest.status_code,
            )

    if wrong_answer_repetitions is not None:
        if wrong_answer_repetitions >= 0:
            user_settings.wrong_answer_repetitions = wrong_answer_repetitions
        else:
            return Response(
                "Wrong answer repetitions must be greater or equal to 0",
                status=HttpResponseBadRequest.status_code,
            )

    user_settings.save()
    return Response(status=200)


async def refresh_user_data(request):
    try:
        request_user = await aget_user(request)
        await update_user_data_from_usos(
            access_token=request_user.access_token,
            access_token_secret=request_user.access_token_secret,
        )
    except Exception as e:
        messages.error(
            request, f"Wystąpił błąd podczas odświeżania danych użytkownika: {e}"
        )
    return redirect(request.GET.get("next", "index"))


@api_view(["GET"])
def api_current_user(request):
    serializer = UserSerializer(request.user)
    return Response(serializer.data)
