"""Poll the latest display telemetry without a Python callback per DDS sample."""
import threading


class LatestTelemetrySubscriber:
    def __init__(self, topic, message_type, interval=0.05):
        from unitree_sdk2py.core.channel import ChannelFactory
        self.channel = ChannelFactory().CreateChannel(topic, message_type)
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    def Init(self, handler, queue_len=1):
        from cyclonedds.qos import Qos, Policy
        # LowState is published near 1 kHz. Keep only the latest sample in
        # native DDS, and deserialize it at the UI rate instead of on recvMC.
        self.channel.SetReader(Qos(Policy.History.KeepLast(1), Policy.Reliability.BestEffort))

        def poll():
            while not self.stop_event.is_set():
                message = self.channel.Read(timeout=0.1)
                if message is not None:
                    handler(message)
                self.stop_event.wait(self.interval)

        self.thread = threading.Thread(target=poll, name="imu-latest", daemon=True)
        self.thread.start()

    def Close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        # Close only once; telemetry lifecycle may call Close twice.
        if self.channel is not None and (self.thread is None or not self.thread.is_alive()):
            self.channel.CloseReader()
            self.channel = None
