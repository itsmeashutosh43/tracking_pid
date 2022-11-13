cmake_minimum_required(VERSION 3.0.2)
project(tracking_pid)
find_package(catkin REQUIRED dynamic_reconfigure message_generation)
generate_dynamic_reconfigure_options(
  cfg/Params.cfg
)

add_message_files(
  FILES
  state.msg 
  states.msg 
)

generate_messages(
  DEPENDENCIES
  std_msgs
)
catkin_package(CATKIN_DEPENDS message_runtime)
include_directories()
catkin_install_python(PROGRAMS
  scripts/tracking_pid_node.py
  scripts/vicon_to_odom_node.py
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)
