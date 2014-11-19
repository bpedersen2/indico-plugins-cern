from setuptools import setup, find_packages


setup(
    name='indico_outlook',
    version='0.1',
    url='https://gitlab.cern.ch/indico/indico-plugin-outlook',
    author='Indico Team',
    author_email='indico-team@cern.ch',
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=[
        'indico>=1.9.1'
    ],
    entry_points={'indico.plugins': {'outlook = indico_outlook.plugin:OutlookPlugin'},
                  'indico.zodb_importers': {'outlook = indico_outlook.zodbimport:OutlookImporter'}}
)
