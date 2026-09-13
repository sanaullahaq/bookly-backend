import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from src.auth.utils import create_access_token, hash_password
from src.books.schemas import BookCreate
from src.books.service import BookService
from src.db.models import Review, User
from src.errors import ReviewAlreadyExists
from src.reviews.schemas import ReviewCreate
from src.reviews.service import ReviewService


async def _create_book(session, user_uid, title="Dup Review Book"):
    book_service = BookService()
    return await book_service.create_book(
        book_data=BookCreate(
            title=title,
            author="Author",
            publisher="Pub",
            page_count=100,
            language="English",
            published_date="2024-01-01",
        ),
        user_uid=user_uid,
        session=session,
    )


async def _review_count(session, book_uid=None):
    stmt = (
        select(Review).where(Review.book_uid == book_uid)
        if book_uid is not None
        else select(Review)
    )
    return len((await session.exec(stmt)).all())


async def _create_verified_user(session, username="seconduser", email="second@example.com"):
    user = User(
        username=username,
        email=email,
        first_name="Second",
        last_name="User",
        role="user",
        is_verified=True,
        password_hash=hash_password("testpass123"),
    )  # type: ignore
    session.add(user)
    await session.flush()
    await session.refresh(user)
    token = create_access_token(
        user_data={"email": user.email, "user_uid": str(user.uid)}
    )
    return user, {"Authorization": f"Bearer {token}"}


class TestDuplicateReviews:
    @pytest.mark.asyncio
    async def test_duplicate_review_returns_409(
        self, client, session, auth_headers, verified_user
    ):
        book = await _create_book(session, verified_user.uid)
        url = f"/api/v1/reviews/book/{book.uid}"

        first = await client.post(
            url,
            json={"rating": 4, "review_text": "Once"},
            headers=auth_headers,
        )
        assert first.status_code == 200

        second = await client.post(
            url,
            json={"rating": 5, "review_text": "Twice"},
            headers=auth_headers,
        )
        assert second.status_code == 409
        body = second.json()
        assert body["error_code"] == "review_already_exists"
        assert body["message"] == "Review Already Exists From The Current User"

        assert await _review_count(session, book_uid=book.uid) == 1

    @pytest.mark.asyncio
    async def test_same_user_can_review_different_books(
        self, client, session, auth_headers, verified_user
    ):
        book_a = await _create_book(session, verified_user.uid, title="Book A")
        book_b = await _create_book(session, verified_user.uid, title="Book B")

        resp_a = await client.post(
            f"/api/v1/reviews/book/{book_a.uid}",
            json={"rating": 3, "review_text": "A"},
            headers=auth_headers,
        )
        resp_b = await client.post(
            f"/api/v1/reviews/book/{book_b.uid}",
            json={"rating": 4, "review_text": "B"},
            headers=auth_headers,
        )
        assert resp_a.status_code == 200
        assert resp_b.status_code == 200
        assert await _review_count(session) == 2

    @pytest.mark.asyncio
    async def test_different_users_can_review_same_book(
        self, client, session, auth_headers, verified_user
    ):
        book = await _create_book(session, verified_user.uid)
        other_user, other_headers = await _create_verified_user(session)
        url = f"/api/v1/reviews/book/{book.uid}"

        r1 = await client.post(
            url,
            json={"rating": 4, "review_text": "from user 1"},
            headers=auth_headers,
        )
        r2 = await client.post(
            url,
            json={"rating": 2, "review_text": "from user 2"},
            headers=other_headers,
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert await _review_count(session, book_uid=book.uid) == 2

    @pytest.mark.asyncio
    async def test_service_raises_review_already_exists_on_duplicate(
        self, session, verified_user
    ):
        book = await _create_book(session, verified_user.uid)
        service = ReviewService()

        ok_review = await service.add_review_to_book(
            user_email=verified_user.email,
            book_uid=str(book.uid),
            review_data=ReviewCreate(rating=3, review_text="Once"),
            session=session,
        )
        assert ok_review is not None

        with pytest.raises(ReviewAlreadyExists):
            await service.add_review_to_book(
                user_email=verified_user.email,
                book_uid=str(book.uid),
                review_data=ReviewCreate(rating=5, review_text="Twice"),
                session=session,
            )

    @pytest.mark.asyncio
    async def test_db_unique_constraint_rejects_duplicate_insert(
        self, session, verified_user
    ):
        book = await _create_book(session, verified_user.uid)

        first = Review(
            rating=4,
            review_text="First",
            user_uid=verified_user.uid,
            book_uid=book.uid,
        )
        duplicate = Review(
            rating=5,
            review_text="Second",
            user_uid=verified_user.uid,
            book_uid=book.uid,
        )
        session.add_all([first, duplicate])

        with pytest.raises(IntegrityError):
            await session.flush()

    @pytest.mark.asyncio
    async def test_integrity_error_returns_409(
        self, client, session, auth_headers, verified_user, monkeypatch
    ):
        book = await _create_book(session, verified_user.uid)
        book_uid_str = str(book.uid)

        async def failing_commit(*args, **kwargs):
            raise IntegrityError(
                "INSERT INTO reviews",
                {},
                RuntimeError("duplicate key value violates unique constraint"),
            )

        monkeypatch.setattr(session, "commit", failing_commit)

        resp = await client.post(
            f"/api/v1/reviews/book/{book_uid_str}",
            json={"rating": 4, "review_text": "Race loser"},
            headers=auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["error_code"] == "review_already_exists"
        assert await _review_count(session, book_uid_str) == 0