from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("conversation", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM pg_indexes
                            WHERE schemaname = 'public' AND indexname = 'convsession_doc_user_active_idx'
                        ) THEN
                            ALTER INDEX "convsession_doc_user_active_idx" RENAME TO "conv_doc_user_active_idx";
                        END IF;

                        IF EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'uniq_active_session_per_document_user'
                        ) THEN
                            ALTER TABLE "documentsession"
                            RENAME CONSTRAINT "uniq_active_session_per_document_user"
                            TO "uniq_active_doc_user";
                        END IF;
                    END $$;
                    """,
                    reverse_sql="SELECT 1;",
                ),
            ],
            state_operations=[
                migrations.RemoveConstraint(
                    model_name="documentsession",
                    name="uniq_active_session_per_document_user",
                ),
                migrations.AddConstraint(
                    model_name="documentsession",
                    constraint=models.UniqueConstraint(
                        condition=models.Q(("is_active", True)),
                        fields=("document", "user"),
                        name="uniq_active_doc_user",
                    ),
                ),
                migrations.RenameIndex(
                    model_name="documentsession",
                    old_name="convsession_doc_user_active_idx",
                    new_name="conv_doc_user_active_idx",
                ),
            ],
        ),
    ]
