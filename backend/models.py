# Data models

from typing import Literal

from pydantic import BaseModel, Field

LeadStatus = Literal["lead", "mql", "sql", "hot", "client", "repeat", "drain_mql", "drain_sql", "drain_hot"]


class Lead(BaseModel):
    id: int | None = Field(default=None, description="Автоинкремент, первичный ключ")
    name: str = Field(..., description="Имя клиента")
    phone: str = Field(default="", description="Телефон")
    extra_phones: str = Field(default="", description="Дополнительные номера телефона")
    avito_link: str = Field(default="", description="Ссылка на Авито")
    max_link: str = Field(default="", description="Ссылка на МАХ")
    tg_link: str = Field(default="", description="Ссылка на Telegram")
    address: str = Field(default="", description="Адрес объекта")
    object_type: str = Field(..., description="Тип объекта")
    budget: str = Field(..., description="Бюджет")
    status: LeadStatus = Field(..., description="Статус лида")
    last_contact: str = Field(default="", description="Дата последнего контакта")
    comment: str = Field(default="", description="Комментарий")
    work_types: list[str] = Field(default_factory=list, description="Виды работ — JSON-массив строк")
    description: str = Field(default="", description="Текстовое описание проекта")
    deal_amount: int | None = Field(default=None, description="Сумма сделки в рублях, может быть пустым")
    communication_done: bool = Field(default=False, description="Завершил общение — не показывать в «Требуют внимания»")
    has_multiple_objects: bool = Field(default=False, description="У клиента несколько объектов")
    created_at: str | None = Field(default=None, description="Дата создания, заполняется автоматически")


class LeadObject(BaseModel):
    id: int | None = Field(default=None, description="Автоинкремент")
    lead_id: int = Field(..., description="Внешний ключ на leads.id")
    name: str = Field(default="Объект", description="Название объекта")
    address: str = Field(default="", description="Адрес")
    object_type: str = Field(default="Квартира", description="Тип объекта")
    budget: str = Field(default="lo", description="Бюджет")
    work_types: list[str] = Field(default_factory=list, description="Виды работ — JSON-массив строк")
    description: str = Field(default="", description="Описание проекта")
    deal_amount: int | None = Field(default=None, description="Сумма сделки в рублях")
    last_contact: str = Field(default="", description="Дата последнего контакта по объекту")
    sort_order: int = Field(default=0, description="Порядок отображения")


class LeadObjectCreate(BaseModel):
    name: str = Field(default="Объект", description="Название объекта")
    address: str = Field(default="", description="Адрес")
    object_type: str = Field(default="Квартира", description="Тип объекта")
    budget: str = Field(default="lo", description="Бюджет")
    work_types: list[str] = Field(default_factory=list, description="Виды работ")
    description: str = Field(default="", description="Описание проекта")
    deal_amount: int | None = Field(default=None, description="Сумма сделки в рублях")
    last_contact: str = Field(default="", description="Дата последнего контакта по объекту")
    sort_order: int = Field(default=0, description="Порядок отображения")


class Note(BaseModel):
    id: int | None = Field(default=None, description="Автоинкремент")
    lead_id: int = Field(..., description="Внешний ключ на leads.id")
    lead_object_id: int | None = Field(default=None, description="Внешний ключ на lead_objects.id, null = один объект")
    text: str = Field(..., description="Текст заметки")
    created_at: str | None = Field(default=None, description="Дата и время создания, заполняется автоматически")


class NoteCreate(BaseModel):
    text: str = Field(..., description="Текст заметки")
    lead_object_id: int | None = Field(default=None, description="Привязка к объекту при нескольких объектах")


class Message(BaseModel):
    id: int | None = Field(default=None, description="Автоинкремент")
    lead_id: int = Field(..., description="Внешний ключ на leads.id")
    text: str = Field(..., description="Текст сообщения")
    direction: str = Field(..., description="in / out / unknown")
    source: str = Field(..., description="Авито, Телеграм, WhatsApp, Телефон")
    created_at: str | None = Field(default=None, description="Дата и время")


class MessageCreate(BaseModel):
    text: str = Field(..., description="Текст сообщения")
    direction: str = Field(..., description="in / out / unknown")
    source: str = Field(..., description="Источник")


class MessageBulkItem(BaseModel):
    text: str = Field(..., description="Текст сообщения")
    direction: str = Field(..., description="in / out / unknown")
    source: str = Field(..., description="Источник")
    created_at: str | None = Field(default=None, description="Дата и время (опционально)")


class MessageDirectionUpdate(BaseModel):
    direction: str = Field(..., description="in / out")
