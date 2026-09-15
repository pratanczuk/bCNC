"""Persisted settings owned by the current application.

Bundled defaults define ordinary options; these are the additional runtime and
user-created values. Firmware error rules are intentionally command-keyed.
"""
EXTRA = {
    'bCNC': 'language width height windowstate lastcheck',
    'Connection': '',
    'Plotter': 'pressure speed knife_offset overcut mat_width mat_height load_distance auto_dragknife profile_library blade_profiles material_profiles recent_projects',
    'File': 'recent.0 recent.1 recent.2 recent.3 recent.4 recent.5 recent.6 recent.7 recent.8 recent.9',
    'TextInsertion': 'font height',
    'CNC': 'acceleration_a acceleration_b acceleration_c feedmax_a feedmax_b feedmax_c travel_a travel_b travel_c',
}


def used_option(defaults, section, key):
    if section == 'Error':
        return True  # CNC compiler command-handling overrides.
    if section == 'Controller':
        return key.startswith('grbl_') and key[5:].isdigit()
    return defaults.has_option(section, key) or key in EXTRA.get(section, '').split()


def migrate_job_defaults(config):
    """Upgrade exact former templates in preferences, never project blocks."""
    old = {
        'header': {'M3 S220 F1500', '$H\n$G\nM3 S220 F1500'},
        'footer': {'G4 P0.1', 'G4 P0.1\nM5\n$H', 'G4 P0.1\nM5\n$H\n$G\nG0 Y0'},
    }
    new = {'header': 'M5\nG21 G90 G17 G94', 'footer': 'M5'}
    for key, templates in old.items():
        if config.has_option('CNC', key):
            value = '\n'.join(line.strip().upper() for line in config.get('CNC', key).splitlines() if line.strip())
            if value in {template.upper() for template in templates}:
                config.set('CNC', key, new[key])
