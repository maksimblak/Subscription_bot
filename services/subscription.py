import logging
from datetime import datetime
from typing import Optional, List
from aiogram import Bot
from aiogram.types import ChatMemberMember, ChatMemberAdministrator, ChatMemberOwner
from aiogram.exceptions import TelegramBadRequest

from config import MAIN_CHANNEL_ID, CHANNELS_CONFIG
from database.models import UserModel, ChannelModel, UserChannelModel, UserModelExtended, ActionLogModel
from utils.helpers import days_since, parse_date

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
            logger.error(f"Ошибка Telegram при создании invite link для канала {channel_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при создании invite link для канала {channel_id}: {e}")
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

    async def revoke_unqualified_channel_access(self, user_id: int, channel_id: int, channel_name: str) -> Optional[int]:
        """
        Отозвать доступ пользователя к каналу, если он не соответствует требованиям.
        Возвращает message_id для удаления или None.
        """
        # Получаем message_id перед удалением
        channels = await UserChannelModel.get_user_channels(user_id)
        message_id = None
        for ch in channels:
            if ch["channel_id"] == channel_id:
                message_id = ch.get("message_id")
                break

        # Удаляем запись о доступе из БД
        await UserChannelModel.revoke_access(user_id, channel_id)

        # Удаляем пользователя из канала (ban + unban)
        try:
            await self.bot.ban_chat_member(channel_id, user_id)
            await self.bot.unban_chat_member(channel_id, user_id, only_if_banned=True)
            logger.info(f"Пользователь {user_id} удалён из канала {channel_name} (недостаточно дней подписки)")
        except TelegramBadRequest as e:
            logger.warning(f"Не удалось удалить пользователя {user_id} из канала {channel_id}: {e}")

        # Уведомляем пользователя
        try:
            await self.bot.send_message(
                user_id,
                f"⚠️ <b>Доступ к каналу «{channel_name}» был отозван</b>\n\n"
                f"Причина: недостаточное количество дней подписки на материнский канал.\n\n"
                f"Продолжайте подписку, и доступ будет восстановлен автоматически!",
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            logger.warning(f"Не удалось отправить уведомление пользователю {user_id}: {e}")

        return message_id

    async def check_and_revoke_unqualified_access(self) -> dict:
        """
        Проверить всех пользователей с доступом к каналам и удалить тех,
        кто не соответствует требованиям по дням подписки.
        """
        stats = {
            "checked_channels": 0,
            "revoked_access": 0,
            "errors": 0
        }

        for channel_config in CHANNELS_CONFIG:
            channel_id = channel_config["id"]
            days_required = channel_config["days_required"]
            channel_name = channel_config["name"]

            if channel_id == 0:
                continue

            stats["checked_channels"] += 1

            # Получаем всех пользователей с доступом к этому каналу
            users_with_access = await UserChannelModel.get_users_with_channel_access(channel_id)

            for user_info in users_with_access:
                user_id = user_info["user_id"]

                try:
                    # Проверяем эффективное количество дней
                    effective_days = await UserModelExtended.get_effective_days(user_id)

                    # Если дней меньше, чем требуется - отзываем доступ
                    if effective_days < days_required:
                        message_id = await self.revoke_unqualified_channel_access(
                            user_id, channel_id, channel_name
                        )

                        # Удаляем сообщение с invite-ссылкой
                        if message_id:
                            try:
                                await self.bot.delete_message(user_id, message_id)
                            except Exception as e:
                                logger.warning(f"Не удалось удалить сообщение {message_id}: {e}")

                        # Логируем
                        await ActionLogModel.log(
                            ActionLogModel.CHANNEL_ACCESS_REVOKED,
                            user_id,
                            f"channel: {channel_name}, reason: insufficient days ({effective_days} < {days_required})"
                        )

                        stats["revoked_access"] += 1

                except Exception as e:
                    logger.error(f"Ошибка при проверке пользователя {user_id} для канала {channel_id}: {e}")
                    stats["errors"] += 1

        return stats

    async def get_available_channels(self, user_id: int) -> List[dict]:
        """
        Получить список каналов, к которым пользователь может получить доступ.
        """
        user = await UserModel.get(user_id)
        if not user or not user["is_active"]:
            return []

        join_date = parse_date(user["join_date"])
        if join_date is None:
            logger.warning(f"Невозможно распарсить дату для пользователя {user_id}: {user['join_date']}")
            return []
        # Используем эффективные дни (реальные + бонусные)
        days_subscribed = await UserModelExtended.get_effective_days(user_id)

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

        # Используем эффективные дни (реальные + бонусные)
        days_subscribed = await UserModelExtended.get_effective_days(user_id)
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
            "unqualified_revoked": 0,
            "errors": 0
        }

        # Сначала проверяем и удаляем пользователей, которые не соответствуют требованиям
        revoke_stats = await self.check_and_revoke_unqualified_access()
        stats["unqualified_revoked"] = revoke_stats["revoked_access"]
        stats["errors"] += revoke_stats["errors"]

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
