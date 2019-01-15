from setuptools import setup, find_packages

setup(name='django-softdelete-gt',
      version='0.10.0',
      description='Soft delete support for Django ORM, with undelete and many more!',
      author='GyroTools LLC',
      author_email='info@gyrotools.com',
      maintainer='GyroTools',
      maintainer_email='felix.eichenberger@gyrotools.com',
      license="BSD",
      url="https://github.com/GyroTools/django-softdelete.git",
      packages=find_packages(),
      install_requires=['setuptools',],
      include_package_data=True,
      setup_requires=['setuptools_hg',],
      classifiers=[
        'Framework :: Django',
        'License :: OSI Approved :: BSD License',
        'Environment :: Web Environment',
        ]
)
