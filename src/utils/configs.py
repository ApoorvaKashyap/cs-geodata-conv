from configparser import ConfigParser

sysconfig = ConfigParser()
sysconfig.read("configs/sysconf.ini")

userconfig = ConfigParser()
userconfig.read("configs/userconf.ini")
