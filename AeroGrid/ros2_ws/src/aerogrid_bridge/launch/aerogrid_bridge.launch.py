"""Launch file for AeroGrid ROS 2 Bridge."""

import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    # Declare launch arguments
    db_path_arg = DeclareLaunchArgument(
        "db_path",
        default_value="",
        description="Path to SQLite WAL audit database (backend/audit/aerogrid_audit.db)",
    )
    poll_frequency_arg = DeclareLaunchArgument(
        "poll_frequency",
        default_value="2.0",
        description="Database polling frequency in Hz",
    )
    topic_name_arg = DeclareLaunchArgument(
        "topic_name",
        default_value="/aerogrid/utm_commands",
        description="ROS 2 topic for publishing operational commands",
    )
    with_mock_sim_arg = DeclareLaunchArgument(
        "with_mock_sim",
        default_value="false",
        description="Launch mock CoppeliaSim simulator node for automated testing",
    )

    # 1. UTM Command Publisher Node (SQLite WAL -> CoppeliaSim)
    utm_bridge_node = Node(
        package="aerogrid_bridge",
        executable="utm_publisher",
        name="utm_bridge_node",
        output="screen",
        parameters=[
            {
                "db_path": LaunchConfiguration("db_path"),
                "poll_frequency": LaunchConfiguration("poll_frequency"),
                "topic_name": LaunchConfiguration("topic_name"),
            }
        ],
    )

    # 2. Telemetry Ingestion Node (CoppeliaSim -> Multi-Agent Arbitration -> SQLite WAL)
    telemetry_bridge_node = Node(
        package="aerogrid_bridge",
        executable="telemetry_bridge",
        name="telemetry_bridge_node",
        output="screen",
        parameters=[
            {
                "db_path": LaunchConfiguration("db_path"),
                "telemetry_topic": "/aerogrid/drone_telemetry",
            }
        ],
    )

    # 3. Optional Mock CoppeliaSim Node
    from launch.conditions import IfCondition
    mock_sim_node = Node(
        package="aerogrid_bridge",
        executable="mock_coppelia_sim",
        name="mock_coppelia_sim_node",
        output="screen",
        condition=IfCondition(LaunchConfiguration("with_mock_sim")),
    )

    return LaunchDescription(
        [
            db_path_arg,
            poll_frequency_arg,
            topic_name_arg,
            with_mock_sim_arg,
            utm_bridge_node,
            telemetry_bridge_node,
            mock_sim_node,
        ]
    )

