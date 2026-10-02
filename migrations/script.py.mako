"""Alembic migration template."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
revision: str = "${up_revision}"
down_revision: Union[str, Sequence[str], None] = "${down_revision}"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    pass
def downgrade() -> None:
    pass
