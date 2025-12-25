import logging
from datetime import datetime
from typing import Optional, List
from aiogram import Bot
from aiogram.types import ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner
from aiogram.exceptions import TelegramBadRequest

from config import MAIN_CHANNEL_ID, CHANNELS_CONFIG
from database.models import UserModel, ChannelModel, UserChannelModel
from utils.helpers import days_since

logger = logging.getLogger(__name__)


class SubscriptionService:
    def __init__(self, bot: Bot):
        self.bot = bot

    async def check_main_subscription(self, user_id: int) -> bool:
        """Проверить подписку на материнский канал."""
        try:
            member = await self.bot.get_chat_member(MAIN_CHANNEL_ID, user_id)
            return isinstance(member, (ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner))
        except TelegramBadRequest:
            return False

    async def register_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None
    ) -> dict:
        """
        Регистрация нового пользователя или возврат существующего.
        Возвращает информацию о пользователе и статус.
        """
        existing_user = await UserModel.get(user_id)

        if existing_user:
            if not existing_user["is_active"]:
                # Реактивация пользователя
                await UserModel.update_active(user_id, True)
                return {"user": existing_user, "status": "reactivated"}
            return {"user": existing_user, "status": "existing"}

        # Создание нового пользователя
        await UserModel.create(user_id, username, first_name)
        user = await UserModel.get(user_id)
        return {"user": user, "status": "new"}

    async def grant_channel_access(self, user_id: int, channel_id: int) -> Optional[str]:
        """
        Выдать доступ к каналу.
        Возвращает invite link или None при ошибке.
        """
        try:
            # Проверяем, есть ли уже доступ
            if await UserChannelModel.has_access(user_id, channel_id):
                return None

            # Создаем одноразовую ссылку-приглашение
            invite_link = await self.bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1,
                name=f"user_{user_id}"
            )

            # Сохраняем информацию о доступе
            await UserChannelModel.grant_access(user_id, channel_id)

            return invite_link.invite_link
        except TelegramBadRequest as e:
            logger.error(f"Ошибка при создании invite link для канала {channel_id}: {e}")
            return None

    async def revoke_user_access(self, user_id: int) -> List[int]:
        """
        Отозвать все доступы пользователя.
        Возвращает список message_id для удаления.
        """
        channels_info = await UserChannelModel.revoke_all(user_id)
        message_ids = []

        for channel in channels_info:
            channel_id = channel["channel_id"]
            message_id = channel.get("message_id")

            if message_id:
                message_ids.append(message_id)

            # Удаляем пользователя из канала
            try:
                await self.bot.ban_chat_member(channel_id, user_id)
                # Сразу разбаниваем, чтобы мог вернуться позже
                await self.bot.unban_chat_member(channel_id, user_id, only_if_banned=True)
            except TelegramBadRequest as e:
                logger.warning(f"Не удалось удалить пользователя {user_id} из канала {channel_id}: {e}")

        # Обновляем статус пользователя
        await UserModel.update_active(user_id, False)

        return message_ids

    async def get_available_channels(self, user_id: int) -> List[dict]:
        """
        Получить список каналов, к которым пользователь может получить доступ.
        """
        user = await UserModel.get(user_id)
        if not user or not user["is_active"]:
            return []

        join_date = datetime.fromisoformat(user["join_date"]) if isinstance(user["join_date"], str) else user["join_date"]
        days_subscribed = days_since(join_date)

        available = []
        for channel_config in CHANNELS_CONFIG:
            if channel_config["days_required"] <= days_subscribed:
                has_access = await UserChannelModel.has_access(user_id, channel_config["id"])
                if not has_access and channel_config["id"] != 0:
                    available.append(channel_config)

        return available

    async def get_user_status(self, user_id: int) -> dict:
        """Получить полный статус пользователя."""
        user = await UserModel.get(user_id)
        if not user:
            return {"exists": False}

        join_date = datetime.fromisoformat(user["join_date"]) if isinstance(user["join_date"], str) else user["join_date"]
        days_subscribed = days_since(join_date)
        user_channels = await UserChannelModel.get_user_channels(user_id)

        return {
            "exists": True,
            "user": user,
            "days_subscribed": days_subscribed,
            "channels_count": len(user_channels),
            "channels": user_channels
        }

    async def process_daily_check(self) -> dict:
        """
        Ежедневная проверка подписок.
        Возвращает статистику обработки.
        """
        stats = {
            "checked": 0,
            "new_access_granted": 0,
            "deactivated": 0,
            "errors": 0
        }

        active_users = await UserModel.get_active_users()

        for user in active_users:
            stats["checked"] += 1
            user_id = user["user_id"]

            try:
                # Проверяем подписку на материнский канал
                is_subscribed = await self.check_main_subscription(user_id)

                if not is_subscribed:
                    # Пользователь отписался
                    await self.revoke_user_access(user_id)
                    stats["deactivated"] += 1
                    continue

                # Проверяем доступные каналы
                available_channels = await self.get_available_channels(user_id)
                for channel in available_channels:
                    invite_link = await self.grant_channel_access(user_id, channel["id"])
                    if invite_link:
                        # Отправляем сообщение пользователю
                        try:
                            msg = await self.bot.send_message(
                                user_id,
                                f"🎉 Поздравляем! Вам открыт доступ к каналу <b>{channel['name']}</b>!\n\n"
                                f"Ссылка для подписки: {invite_link}\n\n"
                                f"⚠️ Ссылка одноразовая, используйте её для присоединения.",
                                parse_mode="HTML"
                            )
                            # Сохраняем message_id
                            await UserChannelModel.update_message_id(
                                user_id, channel["id"], msg.message_id
                            )
                            stats["new_access_granted"] += 1
                        except TelegramBadRequest as e:
                            logger.warning(f"Не удалось отправить сообщение пользователю {user_id}: {e}")

            except Exception as e:
                logger.error(f"Ошибка при обработке пользователя {user_id}: {e}")
                stats["errors"] += 1

        return stats
