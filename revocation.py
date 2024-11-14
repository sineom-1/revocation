'''
Author: sineom h.sineom@gmail.com
Date: 2024-11-11 14:17:56
LastEditors: sineom h.sineom@gmail.com
LastEditTime: 2024-11-14 10:33:56
FilePath: /anti_withdrawal/revocation.py
Description: 防止撤回消息

Copyright (c) 2024 by sineom, All Rights Reserved. 
'''
from bridge.context import ContextType
from channel.chat_message import ChatMessage
import plugins
import json
import os
import re
from threading import Timer
import time
from plugins import *
from common.log import logger
from lib.itchat.content import *
from lib import itchat

@plugins.register(
    name="Revocation",
    desire_priority=-1,
    namecn="防止撤回",
    desc="防止微信消息撤回插件",
    version="1.1",
    author="sineom",
)
class Revocation(Plugin):
    def __init__(self):
        super().__init__()
        self.config = super().load_config()
        if not self.config:
            # 未加载到配置，使用模板中的配置
            self.config = self._load_config_template()
        self.handlers[Event.ON_RECEIVE_MESSAGE] = self.on_receive_message
        logger.info("[Revocation] inited")
        # 初始化存储
        self.msg_dict = {}
        self.out_date_msg_dict = []
        self.target_friend = None
        self.download_directory = './plugins/revocation/downloads'
        
        # 确保下载目录存在
        if not os.path.exists(self.download_directory):
            os.makedirs(self.download_directory)
            
        # 启动定时清理
        self.start_cleanup_timer()
        self.clear_temp_files() 
    
    def _load_config_template(self):
        logger.debug("No revocation plugin config.json, use plugins/revocation/config.json.template")
        try:
            plugin_config_path = os.path.join(self.path, "config.json.template")
            if os.path.exists(plugin_config_path):
                with open(plugin_config_path, "r", encoding="utf-8") as f:
                    plugin_conf = json.load(f)
                    return plugin_conf
        except Exception as e:
            logger.exception(e)

    def clear_temp_files(self):
        """首次启动，将临时目录下的文件全部清除"""
        for file in os.listdir(self.download_directory):
            os.remove(os.path.join(self.download_directory, file))


    def get_help_text(self, **kwargs):
        help_text = "防撤回插件使用说明:\n"
        help_text += "本插件会自动保存最近消息并在检测到撤回时转发给指定接收者\n\n"
        return help_text

    def get_revoke_msg_receiver(self):
        """获取接收撤回消息的好友"""
        if self.target_friend is None:
            friends = itchat.get_friends(update=True)
            receiver_config = self.config.get("receiver", {})
            match_type = receiver_config.get("type", "remark_name")
            match_name = receiver_config.get("name", "")
            
            for friend in friends:
                if match_type == "nickname" and friend['NickName'] == match_name:
                    self.target_friend = friend
                    break
                elif match_type == "remark_name" and friend['RemarkName'] == match_name:
                    self.target_friend = friend
                    break
                    
            if self.target_friend is None:
                logger.error(f"[AntiWithdrawal] 未找到接收者: {match_type}={match_name}")
                
        return self.target_friend

    def start_cleanup_timer(self):
        """启动定时清理"""
        def delete_out_date_msg():
            current_time = int(time.time())
            expire_time = self.config.get("message_expire_time", 120)
            # 找出过期消息
            expired_msg_ids = []
            for msg_id, msg in list(self.msg_dict.items()):
                if (current_time - msg.create_time) > expire_time:
                    expired_msg_ids.append(msg_id)
                    # 删除过期消息
                    if msg.ctype == ContextType.TEXT:
                        self.msg_dict.pop(msg_id)
                    elif msg.ctype in [ContextType.IMAGE, ContextType.VIDEO, ContextType.FILE]:
                        file_path = msg.content
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        self.msg_dict.pop(msg_id)
            
            cleanup_interval = self.config.get("cleanup_interval", 2)
            t = Timer(cleanup_interval, delete_out_date_msg)
            t.start()
            
        delete_out_date_msg()

    def download_files(self, msg):
        """下载文件"""
        if not msg._prepared:
            msg._prepare_fn()
            msg._prepared = True
        return msg.content
            

    def handle_revoke(self, msg, is_group=False):
        """处理撤回消息"""
        match = re.search('撤回了一条消息', msg.content)
        if not match:
            return
            
        old_msg_id = re.search(r"\<msgid\>(.*?)\<\/msgid\>", msg.content).group(1)
        if old_msg_id not in self.msg_dict:
            return
            
        old_msg = self.msg_dict[old_msg_id]
        target_friend = self.get_revoke_msg_receiver()
        if target_friend is None:
            return

        try:
            if old_msg.ctype == ContextType.TEXT:
                # 构造消息前缀:
                # 如果是群消息(is_group=True), 前缀格式为: "群：【群名称】的【发送者昵称】"
                # 如果是私聊消息(is_group=False), 前缀格式为: "【发送者昵称】"
                prefix = f"群：【{msg.from_user_nickname}】的【{msg.actual_user_nickname}】" if is_group else f"【{msg.from_user_nickname}】"
                text = f"{prefix}刚刚发过这条消息：{old_msg.content}"
                itchat.send(msg=text, toUserName=target_friend['UserName'])
                
            elif old_msg.ctype in [ContextType.IMAGE, ContextType.VIDEO, ContextType.FILE]:
                msg_type = {ContextType.IMAGE: '图片', ContextType.VIDEO: '视频', ContextType.FILE: '文件'}[old_msg.ctype]
                prefix = f"群：【{msg.from_user_nickname}】的【{msg.actual_user_nickname}】" if is_group else f"【{msg.from_user_nickname}】"
                text = f"{prefix}刚刚发过这条{msg_type}👇"
                itchat.send_msg(msg=text, toUserName=target_friend['UserName'])
                
                file_info = old_msg.content
                if old_msg.ctype == ContextType.IMAGE:
                    itchat.send_image(file_info, toUserName=target_friend['UserName'])
                elif old_msg.ctype == ContextType.VIDEO:
                    itchat.send_video(file_info, toUserName=target_friend['UserName'])
                else:
                    itchat.send_file(file_info, toUserName=target_friend['UserName'])
        except Exception as e:
            logger.error(f"发送撤回消息失败: {str(e)}")

    def handle_msg(self, msg, is_group=False):
        """处理消息"""
        try:
            if msg.ctype == ContextType.REVOKE:
                self.handle_revoke(msg, is_group)
                return
            
            
            
            msg_id = msg.msg_id
            create_time = msg.create_time
            # 超过2分钟的消息丢弃
            if int(create_time) < int(time.time()) - 120:
                return
                
            if msg.ctype == ContextType.TEXT:
                self.msg_dict[msg_id] = msg
            elif msg.ctype in [ContextType.IMAGE, ContextType.VIDEO, ContextType.FILE]:
                # 将 原目录替换为下载目录 原目录只保留文件名称+下载目录
                msg.content = self.download_directory + "/" + os.path.basename(msg.content)
                self.msg_dict[msg_id] = msg
                self.download_files(msg)
                
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")
    
    def on_receive_message(self, e_context: EventContext):
        try:
            logger.debug("[Revocation] on_receive_message: %s" % e_context)
            context = e_context['context']
            cmsg: ChatMessage = context['msg']
            if cmsg.is_group:
                self.handle_group_msg(cmsg)
            else:
                self.handle_single_msg(cmsg)
        except Exception as e:
            logger.error(f"处理消息失败: {str(e)}")

    def handle_single_msg(self, msg):
        """处理私聊消息"""
        self.handle_msg(msg, False)
        return None

    def handle_group_msg(self, msg):
        """处理群聊消息"""
        self.handle_msg(msg, True)
        return None