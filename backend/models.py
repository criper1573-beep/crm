# Data models

from typing import Literal

from pydantic import BaseModel, Field

LeadStatus = Literal["lead", "mql", "sql", "hot", "client", "repeat", "drain_mql", "drain_sql", "drain_hot"]


class Lead(BaseModel):
    id: int | None = Field(default=None, description="Автоинкремент, первичный ключ")
    name: str = Field(..., description="Имя клиента")
    phone: str = Field(default="", description="Телефон")
    avito_link: str = Field(default="", description="Ссылка на Авито")
    address: str = Field(default="", description="Адрес объекта")
    object_type: str = Field(..., description="Тип объекта")
    budget: str = Field(..., description="Бюджет")
    status: LeadStatus = Field(..., description="Статус лида")
    last_contact: str = Field(default="", description="Дата последнего контакта")
    comment: str = Field(default="", description="Комментарий")
    created_at: str | None = Field(default=None, description="Дата создания, заполняется автоматически")
