# Generated by Django 5.1.4 on 2025-01-17 15:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quizzes", "0007_alter_quiz_visibility"),
    ]

    operations = [
        migrations.AlterField(
            model_name="quiz",
            name="visibility",
            field=models.PositiveIntegerField(
                choices=[
                    (0, "Prywatny"),
                    (1, "Dla udostępnionych"),
                    (2, "Niepubliczny (z linkiem)"),
                    (3, "Publiczny"),
                ],
                default=2,
            ),
        ),
    ]
