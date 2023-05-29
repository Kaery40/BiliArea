import sched
import time
import os
import random
from datetime import datetime
from http.cookies import SimpleCookie
import requests
import logging
import threading

# 配置日志对象
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('log.txt')
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[提示] %(message)s')
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_formatter = logging.Formatter('[提示] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
console_handler.setFormatter(console_formatter)
handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(handler)

# 检查文件是否存在，如不存在则创建
if not os.path.exists("bilicookie.save"):
    logger.info("未找到 bilicookie.save 文件，已为您生成")
    with open("bilicookie.save", "w") as f:
        pass

# 读取cookies文件，获取cookie列表
def read_cookies_file(file_name):
    cookies_list = []
    with open(file_name, "r") as f:
        for line in f.readlines():
            cookie = line.strip()
            if cookie:
                cookies_list.append(cookie)
    return cookies_list

# b站直播间信息类
class RoomInfo():
    ChatArea = 740
    JokeArea = 624
    MovieArea = 33

    def __init__(self, data) -> None:
        self.room_id = data.get("room_id")
        self.title = data.get("title")
        self.fc_num = data.get("fc_num")
        self.num = data.get("num")
        self.area_name = data.get("area_v2_name")
        self.have_live = data.get("live_status")
        self.watched_show = data.get("watched_show", {}).get("text_large")

    def isJokeArea(self):
        return "搞笑" == self.area_name

    def isMovieArea(self):
        return "影音馆" == self.area_name
        
    def isChatArea(self):
        return "聊天室" == self.area_name

# bilibili类
class BiliHelper():

    def __init__(self, cookie, index) -> None:
        self._cookies = cookie
        self._request = requests.Session()
        s = SimpleCookie(self._cookies)
        self._bili_jct = s.get("bili_jct").value
        self._index = index

        self._deal_id = set()
        self._headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36 Edg/108.0.1462.54",
            "cookie": self._cookies
        }
        info = self.getInfo()
        self.room_id = info.room_id# 房间号
        self.fc_num = info.fc_num  # 定义并初始化关注数属性
        self.watched_show = info.watched_show  # 定义并初始化直播看过次数属性

        self._schedule = sched.scheduler(time.time, time.sleep)
        self.fc_num = info.fc_num  
        self.watched_show = info.watched_show

    def turnArea(self):
        ok = False
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        now_hour = datetime.now().hour
        if (now_hour >= 2 and now_hour < 9) or (now_hour >= 16 and now_hour < 18):
            # 处于指定时间范围内，不进行切换，并重新启动定时器
            self._schedule.enter(60, 2, self.turnArea, ())
            self._schedule.run()
            return

        info = self.getInfo()
        if (now_hour >= 1 and now_hour < 8 and datetime.now().minute >= 30) or (now_hour >= 15 and now_hour < 18 and datetime.now().minute >= 30 and now_hour != 18):
            # 在早上1点30分-8点30分和下午15点30分-18点30检测当前所在区域，如果不在影音馆则自动切换到影音馆
            info = self.getInfo()
            if not info.isMovieArea():
                ok = self.updateArea(info.MovieArea, info)
                self.fc_num = info.fc_num  
                self.watched_show = info.watched_show
                logger.info("[账号%s][%s][房间-%s] 当前在时区范围内，已切换到【影音馆】   [关注:%s人-%s]" % (self._index, current_time, self.room_id, self.fc_num, self.watched_show))
            else:
                logger.info("[账号%s][%s][房间-%s] 当前在影音馆，无需切换   [关注:%s人-%s]" % (self._index, current_time, self.room_id, self.fc_num, self.watched_show))
        elif info.isJokeArea():
            # 切换到聊天室
            ok = self.updateArea(info.ChatArea, info)
            self.fc_num = info.fc_num  
            self.watched_show = info.watched_show
            logger.info("[账号%s][%s][房间-%s] 当前在搞笑区，切换到【聊天室】30分钟后切换   [关注:%s人-%s]" % (self._index, current_time, self.room_id, self.fc_num, self.watched_show))
        elif info.isChatArea():
            # 切换到影音馆
            ok = self.updateArea(info.MovieArea, info)
            self.fc_num = info.fc_num  
            self.watched_show = info.watched_show
            logger.info("[账号%s][%s][房间-%s] 当前在聊天室，切换到【影音馆】30分钟后切换   [关注:%s人-%s]" % (self._index, current_time, self.room_id, self.fc_num, self.watched_show))
        else:
            # 切换到搞笑区
            ok = self.updateArea(info.JokeArea, info)
            self.fc_num = info.fc_num  
            self.watched_show = info.watched_show
            logger.info("[账号%s][%s][房间-%s] 当前在影音馆，切换到【搞笑区】30分钟后切换   [关注:%s人-%s]" % (self._index, current_time, self.room_id, self.fc_num, self.watched_show))         

        if ok:
            self._schedule.enter(30 * 60, 2, self.turnArea, ())
            self._schedule.run()
        else:
            logger.info("[账号%s][%s][房间-%s] 分区切换失败，等待10秒继续执行" % (self._index, current_time, self.room_id))
            self._schedule.enter(10, 2, self.turnArea, ())
            self._schedule.run()
    
    def updateArea(self, area_id, info: RoomInfo):
        url = "https://api.live.bilibili.com/room/v1/Room/update"
        data = {
            "room_id": info.room_id,
            "area_id": area_id,
            "csrf_token": self._bili_jct,
            "csrf": self._bili_jct
        }
        resp = self._request.post(url, data=data, headers=self._headers)
        resp_json = resp.json()
        if resp_json.get("code") == 0:
            # 请求成功
            return True
        else:
            logger.error("当前-[%s]直播间请求失败%s" % (self.room_id, resp.text))

    def getInfo(self) -> RoomInfo:
        # 获取房间信息
        url = "https://api.live.bilibili.com/xlive/app-blink/v1/room/GetInfo?platform=pc"
        resp = self._request.get(url, headers=self._headers)
        resp_json = resp.json()
        if resp_json.get("code") == 0:
            # 请求成功
            data = resp_json.get("data", {})
            info = RoomInfo(data)
            return info

def main():
    cookies_list = read_cookies_file("bilicookie.save")
    valid_cookie_num = 0
    bili_helpers = []
    threads = []
    for i, cookies in enumerate(cookies_list):
        if not cookies:
            continue
        helper = BiliHelper(cookies, i + 1)
        # 检查cookie是否有效
        if helper.getInfo().room_id:
            valid_cookie_num += 1
            bili_helpers.append(helper)
            t = threading.Thread(target=helper.turnArea)
            threads.append(t)

    logger.info("欢迎使用，检测到[%s]个有效账号。" % valid_cookie_num)
    for t in threads:
        t.start()

    for t in threads:
        t.join()

if __name__ == "__main__":
    main()
