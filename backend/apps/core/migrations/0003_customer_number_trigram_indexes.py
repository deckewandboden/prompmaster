from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0002_search_indexes'),
        ('companies', '0002_rename_companies_c_name_idx_companies_c_name_2d8260_idx_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_company_customer_number_trgm '
            'ON companies_company USING gin (customer_number gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_company_customer_number_trgm;',
        ),
        migrations.RunSQL(
            'CREATE INDEX IF NOT EXISTS pm_private_customer_number_trgm '
            'ON companies_privatecustomerprofile USING gin (customer_number gin_trgm_ops);',
            'DROP INDEX IF EXISTS pm_private_customer_number_trgm;',
        ),
    ]
