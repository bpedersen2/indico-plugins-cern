"""Use ACL settings

Revision ID: 429c381aa08f
Revises: None
Create Date: 2015-05-13 15:09:37.415361
"""

from alembic import context

from indico.core.db.sqlalchemy.util.convert_acl_settings import json_to_acl, acl_to_json


# revision identifiers, used by Alembic.
revision = '429c381aa08f'
down_revision = None


acl_settings = {'plugin_audiovisual.managers'}


def upgrade():
    if context.is_offline_mode():
        raise Exception('This upgrade is only possible in online mode')
    json_to_acl(acl_settings)


def downgrade():
    if context.is_offline_mode():
        raise Exception('This downgrade is only possible in online mode')
    acl_to_json(acl_settings)