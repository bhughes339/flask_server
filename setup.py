from setuptools import setup

setup(
    name='billy_flask',
    version='0.0.1',
    maintainer='William Hughes',
    maintainer_email='me@williamhughes.me',
    description='Billy personal server',
    packages=['billy_flask'],
    include_package_data=True,
    install_requires=[
        'flask', 'requests', 'furl', 'pymysql'
    ],
)
