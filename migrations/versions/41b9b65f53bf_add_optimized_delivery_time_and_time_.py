"""Add optimized_delivery_time and time_saved columns

Revision ID: 41b9b65f53bf
Revises: 
Create Date: 2025-04-02 00:49:06.054345

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '41b9b65f53bf'
down_revision = None  # Set this to the previous revision if you have one
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inefficient_route', schema=None) as batch_op:
        batch_op.add_column(sa.Column('optimized_delivery_time', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('time_saved', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('inefficient_route', schema=None) as batch_op:
        batch_op.drop_column('time_saved')
        batch_op.drop_column('optimized_delivery_time')
