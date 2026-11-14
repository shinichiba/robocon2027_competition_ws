from setuptools import setup
from pathlib import Path

name = 'robot_competition_simulator'
data = [('share/ament_index/resource_index/packages', ['resource/' + name]),
        ('share/' + name, ['package.xml'])]
for folder in ['launch', 'control', 'config', 'robot_maps', 'worlds', 'urdf', 'rviz']:
    for p in Path(folder).rglob('*'):
        if p.is_file():
            data.append((str(Path('share') / name / p.parent), [str(p)]))
setup(
    name=name, version='0.1.0', packages=[name], data_files=data,
    install_requires=['setuptools'], zip_safe=True,
    maintainer='Simulation Team', maintainer_email='team@example.com',
    description='Two robot competition simulation', license='Apache-2.0',
    entry_points={'console_scripts': [
        'competition_manager = robot_competition_simulator.competition_manager:main',
        'robot1_pick_place = robot_competition_simulator.robot1_pick_place:main',
        'odom_tf_splitter = robot_competition_simulator.odom_tf_splitter:main',
        'tf_aggregator = robot_competition_simulator.tf_aggregator:main',
        '1keyboard_control = control.1keyboard_control:main',
        ]})
