-- Pins the coast_region macro to known ports; returns any port it classifies differently.
with known (port, lon, lat, expected) as (
    values
        ('Port of Los Angeles', -118.2755, 33.7547, 'west'),
        ('Seattle', -122.35, 47.58, 'west'),
        ('Vancouver, WA', -122.7037, 45.6349, 'west'),
        ('Houston (Barbours Cut)', -95.1303, 29.7375, 'gulf'),
        ('Port Manatee, FL', -82.56, 27.63, 'gulf'),
        ('Tampa, FL', -82.45, 27.94, 'gulf'),
        ('Mobile, AL', -88.04, 30.71, 'gulf'),
        ('New Orleans, LA', -90.06, 29.95, 'gulf'),
        ('Brownsville, TX', -97.40, 25.95, 'gulf'),
        ('Miami, FL', -80.17, 25.77, 'east'),
        ('Fort Lauderdale, FL', -80.1223, 26.0742, 'east'),
        ('Jacksonville, FL', -81.62, 30.40, 'east'),
        ('Savannah, GA', -81.14, 32.12, 'east'),
        ('Norfolk, VA', -76.33, 36.90, 'east'),
        ('Baltimore, MD', -76.55, 39.25, 'east'),
        ('Newark, NJ', -74.15, 40.68, 'east'),
        ('Boston, MA', -71.03, 42.35, 'east'),
        ('Chicago, IL', -87.63, 41.88, 'inland'),
        ('Cleveland, OH', -81.70, 41.50, 'inland'),
        ('Buffalo, NY', -78.88, 42.88, 'inland'),
        ('Honolulu, HI', -157.87, 21.31, 'noncontiguous'),
        ('Dutch Harbor, AK', -166.54, 53.89, 'noncontiguous'),
        ('Anchorage, AK', -149.89, 61.22, 'noncontiguous'),
        ('San Juan, PR', -66.10, 18.46, 'noncontiguous'),
        ('No coordinates', null::double precision, null::double precision, 'unknown')
)

select port, expected, {{ coast_region('lon', 'lat') }} as actual
from known
where {{ coast_region('lon', 'lat') }} <> expected
