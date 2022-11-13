from dynamic_reconfigure.server import Server
from geometry_msgs.msg import PointStamped, PoseStamped, Twist
from tracking_pid.msg import states
from nav_msgs.msg import Odometry
import numpy as np
import rospy
from std_msgs.msg import Bool
from tf.transformations import euler_from_quaternion
from tracking_pid.cfg import ParamsConfig
from visualization_msgs.msg import Marker
from collections import deque


class TrackingPIDWQueue:

    def __init__(self, odom_topic):
        # Node initialization
        rospy.init_node("tracking_pid")
        # Attributes
        self.prev_linear_vel = 0
        self.prev_angular_vel = 0
        self.twist = Twist()
        self.need_waypoint = Bool()
        self.need_waypoint.data = True
        self.odom = np.empty(5)
        self.waypoint = self.odom[:5].copy()
        self.rotate_lin_vel = 0.2
        self.verbose = True
        self.angular_tolerance = 0.2
        self.robot_radius = 0.2
        self.pid_angular = PID(
            kp=1.0,
            kd=0.0,
            ki=0.0,
            min_output=-1.0,
            max_output=1.0,
            delta=0.01,
            min_integral=0.0,
            max_integral=0.0,
            name="Angular",
        )
        self.pid_linear = PID(
            kp=1.0,
            kd=0.0,
            ki=0.0,
            min_output=-0.5,
            max_output=0.5,
            delta=0.05,
            min_integral=0.0,
            max_integral=0.0,
            name="Linear",
        )
        # Subscribers and Publishers
        self.sub_odom = rospy.Subscriber(
            odom_topic,
            Odometry,
            self.odom_callback,
        )
        self.sub_waypoint = rospy.Subscriber(
            "/states_to_be_followed",
            states,
            self.states_callback,
        )

        self.pub_cmd_vel = rospy.Publisher("/cmd_vel", Twist, queue_size=1)
        # Spinning up
        Server(ParamsConfig, self.param_callback)
        rospy.on_shutdown(self.stop)
        rospy.spin()

    def param_callback(self, config, _):
        self.angular_tolerance = config["angular_tolerance"]
        self.robot_radius = 0.2
        self.rotate_lin_vel = config["rotate_lin_vel"]
        self.verbose = False

        self.pid_angular.kp = config["angular_kp"]
        self.pid_angular.ki = config["angular_ki"]
        self.pid_angular.kd = config["angular_kd"]
        self.pid_angular.min_integral = config["angular_min_integral"]
        self.pid_angular.max_integral = config["angular_max_integral"]
        self.pid_angular.min_output = config["angular_min_output"]
        self.pid_angular.max_output = config["angular_max_output"]
        self.pid_angular.delta = 0.01

        self.pid_linear.kp = config["linear_kp"]
        self.pid_linear.ki = config["linear_ki"]
        self.pid_linear.kd = config["linear_kd"]
        self.pid_linear.min_integral = config["linear_min_integral"]
        self.pid_linear.max_integral = config["linear_max_integral"]
        self.pid_linear.min_output = config["linear_min_output"]
        self.pid_linear.max_output = config["linear_max_output"]
        self.pid_linear.delta = 0.05
        return config

    def stop(self):
        self.twist.linear.x = 0.0
        self.twist.angular.z = 0.0
        self.pub_cmd_vel.publish(self.twist)

    def odom_callback(self, msg):
        self.odom[0] = msg.pose.pose.position.x
        self.odom[1] = msg.pose.pose.position.y

        orientation = msg.pose.pose.orientation
        quaternion = (
            orientation.x,
            orientation.y,
            orientation.z,
            orientation.w,
        )
        self.odom[2] = euler_from_quaternion(quaternion)[2]
        self.odom[3] = msg.twist.twist.linear.x
        self.odom[4] = msg.twist.twist.angular.z
        if self.need_waypoint.data:
            pass
            #  rospy.loginfo("Waiting for new waypoint...")
            # rospy.loginfo(f"x: {self.odom[0]: .2f} | " +
            #              f"y: {self.odom[1]: .2f} | " +
            #              f"θ: {self.odom[2]/np.pi: .2f} π")
        else:
            self.control()

    def states_callback(self, msg):
        states = msg.states
        states = deque(states)
        self.i = 0

        self.states = states

        state = states.popleft()
        self.waypoint[0] = state.x
        self.waypoint[1] = state.y
        self.waypoint[2] = state.yaw
        self.waypoint[3] = state.ux
        self.waypoint[4] = state.utheta

        self.need_waypoint.data = False

    def get_new_waypoint(self):
        rospy.logerr(f"{self.i}th waypoint ...")
        self.i += 1
        state = self.states.popleft()
        self.waypoint[0] = state.x
        self.waypoint[1] = state.y
        self.waypoint[2] = state.yaw
        self.waypoint[3] = state.ux
        self.waypoint[4] = state.utheta
        self.need_waypoint.data = False

    def control(self):
        x_diff = self.waypoint[0] - self.odom[0]
        y_diff = self.waypoint[1] - self.odom[1]
        dist = np.hypot(y_diff, x_diff)
        yaw = self.odom[2]
        x_relative = np.cos(yaw) * x_diff + np.sin(yaw) * \
            y_diff
        y_relative = -np.sin(yaw) * x_diff + np.cos(yaw) * \
            y_diff
        angular_error = np.arctan2(
            y_relative, x_relative)
        linear_error = np.tanh(x_relative)

        #angular_error = (self.waypoint[4] - self.prev_angular_vel)
        #linear_error = self.waypoint[3] - self.prev_linear_vel

        rospy.loginfo(f"Distance: {dist:.2f}")

        self.twist.angular.z = self.pid_angular.update(
            angular_error,
            self.verbose,
        )
        self.twist.linear.x = self.pid_linear.update(
            linear_error,
            self.verbose,
        )

        self.prev_angular_vel = self.twist.angular.z
        self.prev_linear_vel = self.twist.linear.x

        rospy.loginfo(
            f"Linear velocity {self.twist.linear.x} Angular velocity {self.twist.angular.z}")
        if np.abs(angular_error) > self.angular_tolerance:
            self.twist.linear.x = self.rotate_lin_vel
        if dist < self.robot_radius:
            self.need_waypoint.data = True
            self.get_new_waypoint()
            # self.stop()
        self.pub_cmd_vel.publish(self.twist)


class PID:

    def __init__(
        self,
        kp,
        kd,
        ki,
        min_output,
        max_output,
        delta,
        min_integral,
        max_integral,
        name,
    ):
        self.kp = kp
        self.kd = kd
        self.ki = ki
        self.min_output = min_output
        self.max_output = max_output
        self.delta = delta
        self.min_integral = min_integral
        self.max_integral = max_integral
        self.name = name
        self.reset()

    def reset(self):
        self.integral = 0.0
        self.previous_output = 0.0
        self.previous_error = None
        self.previous_time = rospy.Time.now()

    def update(self, error, verbose=True):
        current_time = rospy.Time.now()
        dt = current_time.to_sec() - self.previous_time.to_sec()
        proportional = self.kp * error
        derivative = 0.0
        if dt > 0:
            if self.previous_error is None:
                self.previous_error = error
            derivative = self.kd * (error - self.previous_error) / dt
        self.integral += error * dt
        self.integral = np.clip(
            self.integral,
            self.max_integral,
            self.max_integral,
        )
        integral = self.ki * self.integral
        output = np.clip(
            proportional + integral + derivative,
            self.min_output,
            self.max_output,
        )
        output = np.clip(
            output,
            self.previous_output - self.delta,
            self.previous_output + self.delta,
        )

        self.previous_error = error
        self.previous_time = current_time
        self.previous_output = output

        if verbose:
            debug_msg = f"{self.name}\n"
            debug_msg += f"Error: {error: .2f} | "
            debug_msg += f"P_gain: {proportional: .2f} | "
            debug_msg += f"I_gain: {integral: .2f} | "
            debug_msg += f"D_gain: {derivative: .2f} | "
            debug_msg += f"Output: {output: .2f}"
            rospy.loginfo(debug_msg)
        return output


if __name__ == "__main__":
    try:
        # TrackingPIDWQueue(odom_topic="/odometry/filtered")
        TrackingPIDWQueue(odom_topic="/odom")
    except rospy.ROSInterruptException:
        pass
