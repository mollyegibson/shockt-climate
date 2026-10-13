-- Pins `employee_band_min` to DENUE's band labels; returns any label read differently.
with known (label, expected) as (
    values
        ('0 a 5 personas', 0),
        ('6 a 10 personas', 6),
        ('101 a 250 personas', 101),
        ('251 y más personas', 251),
        ('Más de 250 personas', null)
)

select label, expected, {{ employee_band_min('label') }} as actual
from known
where {{ employee_band_min('label') }} is distinct from expected
