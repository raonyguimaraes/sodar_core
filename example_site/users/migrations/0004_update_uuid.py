# -*- coding: utf-8 -*-
# Generated by Django 1.11.15 on 2018-09-20 15:29
from __future__ import unicode_literals

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_rename_uuid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='sodar_uuid',
            field=models.UUIDField(default=uuid.uuid4, help_text='User SODAR UUID', unique=True),
        ),
    ]