from sqlalchemy import Column, Integer, BigInteger, String, ForeignKey, UniqueConstraint, Boolean
from sqlalchemy.orm import relationship
from bot.database.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String, nullable=True)
    receive_notifications = Column(Boolean, default=True)

    favorites = relationship(
        "Favorite",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select"
    )

class Favorite(Base):
    __tablename__ = "favorites"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    movie_id = Column(Integer, nullable=False)
    movie_title = Column(String, nullable=False)
    movie_overview = Column(String, nullable=True)
    poster_url = Column(String, nullable=True)

    user = relationship("User", back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", name="uq_user_movie"),
    )