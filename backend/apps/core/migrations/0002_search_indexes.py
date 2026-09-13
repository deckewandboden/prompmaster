from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0001_initial'),
        ('accounts', '0001_initial'),
        ('companies', '0001_initial'),
        ('licenses', '0001_initial'),
        ('orders', '0001_initial'),
        ('payments', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            'CREATE EXTENSION IF NOT EXISTS pg_trgm;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_user_email_trgm ON accounts_user USING gin (email gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_user_email_trgm;',
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS pm_user_first_name_trgm ON accounts_user USING gin (first_name gin_trgm_ops);",
            'DROP INDEX IF EXISTS pm_user_first_name_trgm;',
        ),
        migrations.RunSQL(
            "CREATE INDEX IF NOT EXISTS pm_user_last_name_trgm ON accounts_user USING gin (last_name gin_trgm_ops);",
            'DROP INDEX IF EXISTS pm_user_last_name_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_company_name_trgm ON companies_company USING gin (name gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_company_name_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_company_email_trgm ON companies_company USING gin (email gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_company_email_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_license_number_trgm ON licenses_license USING gin (license_number gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_license_number_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_order_number_trgm ON orders_order USING gin (order_number gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_order_number_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_payment_provider_id_trgm ON payments_payment USING gin (provider_payment_id gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_payment_provider_id_trgm;',
        ),
    ]
