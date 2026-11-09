import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'aerogrid_bridge'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='AeroGrid Systems Architect',
    maintainer_email='architect@aerogrid.io',
    description='ROS 2 Humble bridge node publishing AeroGrid UTM operational commands to CoppeliaSim.',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'utm_publisher = aerogrid_bridge.utm_publisher:main',
            'telemetry_bridge = aerogrid_bridge.telemetry_bridge:main',
            'mock_coppelia_sim = aerogrid_bridge.mock_coppelia_sim:main',
        ],
    },
)

