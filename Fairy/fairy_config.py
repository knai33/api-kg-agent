class Config:
    def __init__(self, adb_path, temp_path=None,
                 screenshot_filepath=None,
                 screenshot_filename=None):
        self.adb_path = adb_path
        self.device = None

        self.temp_path = "./tmp" if temp_path is None else temp_path
        self.screenshot_temp_path = self.temp_path + "/screenshot"

        self.screenshot_filepath = "/sdcard" if screenshot_filepath is None else screenshot_filepath
        self.screenshot_filename = "screenshot" if screenshot_filename is None else screenshot_filename

    def get_adb_path(self):
        return (self.adb_path + f" -s {self.device}") if self.device is not None else self.adb_path