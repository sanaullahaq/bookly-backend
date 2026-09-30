import uuid
import pytest
from src.tags.service import TagService
from src.tags.schemas import TagCreate, TagAdd
from src.books.schemas import BookCreate
from src.books.service import BookService
from src.errors import TagAlreadyExists, TagNotFound, BookNotFound


class TestTagService:
    @pytest.mark.asyncio
    async def test_add_tag(self, session):
        service = TagService()
        tag = await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        assert tag.name == "fiction"
        assert isinstance(tag.uid, uuid.UUID)

    @pytest.mark.asyncio
    async def test_add_tag_duplicate(self, session):
        service = TagService()
        await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        with pytest.raises(TagAlreadyExists):
            await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)

    @pytest.mark.asyncio
    async def test_get_tags(self, session):
        service = TagService()
        await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        await service.create_tag(tag_data=TagCreate(name="non-fiction"), session=session)
        tags = await service.get_tags(session=session)
        assert len(tags) >= 2

    @pytest.mark.asyncio
    async def test_get_tag_by_name_found(self, session):
        service = TagService()
        await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        tag = await service.get_tag_by_name(tag_name="fiction", session=session)
        assert tag is not None
        assert tag.name == "fiction"

    @pytest.mark.asyncio
    async def test_get_tag_by_name_not_found(self, session):
        service = TagService()
        tag = await service.get_tag_by_name(tag_name="nonexistent", session=session)
        assert tag is None

    @pytest.mark.asyncio
    async def test_get_tag_by_uid_found(self, session):
        service = TagService()
        created = await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        found = await service.get_tag_by_uid(tag_uid=str(created.uid), session=session)
        assert found is not None
        assert found.name == "fiction"

    @pytest.mark.asyncio
    async def test_get_tag_by_uid_not_found(self, session):
        service = TagService()
        found = await service.get_tag_by_uid(tag_uid=str(uuid.uuid4()), session=session)
        assert found is None

    @pytest.mark.asyncio
    async def test_add_tags_to_book(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Tag Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        result = await tag_service.add_tags_to_book(
            book_uid=str(book.uid),
            tag_data=TagAdd(tags=[TagCreate(name="fiction"), TagCreate(name="classic")]),
            session=session,
        )
        assert len(result.tags) == 2

    @pytest.mark.asyncio
    async def test_add_tags_to_book_not_found(self, session):
        tag_service = TagService()
        with pytest.raises(BookNotFound):
            await tag_service.add_tags_to_book(
                book_uid=str(uuid.uuid4()),
                tag_data=TagAdd(tags=[TagCreate(name="fiction")]),
                session=session,
            )

    @pytest.mark.asyncio
    async def test_update_tag(self, session):
        service = TagService()
        created = await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        updated = await service.update_tag(
            tag_uid=str(created.uid),
            tag_update_data=TagCreate(name="sci-fi"),
            session=session,
        )
        assert updated.name == "sci-fi"

    @pytest.mark.asyncio
    async def test_update_tag_not_found(self, session):
        service = TagService()
        with pytest.raises(TagNotFound):
            await service.update_tag(
                tag_uid=str(uuid.uuid4()),
                tag_update_data=TagCreate(name="sci-fi"),
                session=session,
            )

    @pytest.mark.asyncio
    async def test_delete_tag(self, session):
        service = TagService()
        created = await service.create_tag(tag_data=TagCreate(name="fiction"), session=session)
        await service.delete_tag(tag_uid=str(created.uid), session=session)
        found = await service.get_tag_by_uid(tag_uid=str(created.uid), session=session)
        assert found is None

    @pytest.mark.asyncio
    async def test_delete_tag_not_found(self, session):
        service = TagService()
        with pytest.raises(TagNotFound):
            await service.delete_tag(tag_uid=str(uuid.uuid4()), session=session)

    @pytest.mark.asyncio
    async def test_get_tag_by_uid_malformed(self, session):
        service = TagService()
        found = await service.get_tag_by_uid(tag_uid="not-a-uuid", session=session)
        assert found is None

    @pytest.mark.asyncio
    async def test_add_tags_to_book_deduplicates_names_in_request(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Dedupe Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        result = await tag_service.add_tags_to_book(
            book_uid=str(book.uid),
            tag_data=TagAdd(tags=[TagCreate(name="fiction"), TagCreate(name="fiction")]),
            session=session,
        )
        assert len(result.tags) == 1

    @pytest.mark.asyncio
    async def test_add_tags_to_book_does_not_duplicate_attached_tag(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Reattach Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        tag_payload = TagAdd(tags=[TagCreate(name="fiction")])
        await tag_service.add_tags_to_book(
            book_uid=str(book.uid), tag_data=tag_payload, session=session
        )
        result = await tag_service.add_tags_to_book(
            book_uid=str(book.uid), tag_data=tag_payload, session=session
        )
        assert len(result.tags) == 1

    @pytest.mark.asyncio
    async def test_remove_tag_from_book(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Remove Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        await tag_service.add_tags_to_book(
            book_uid=str(book.uid),
            tag_data=TagAdd(tags=[TagCreate(name="fiction"), TagCreate(name="classic")]),
            session=session,
        )
        tags = await tag_service.get_tags(session=session)
        fiction = next(t for t in tags if t.name == "fiction")

        result = await tag_service.remove_tag_from_book(
            book_uid=str(book.uid), tag_uid=str(fiction.uid), session=session
        )

        assert len(result.tags) == 1
        assert result.tags[0].name == "classic"
        still_exists = await tag_service.get_tag_by_uid(
            tag_uid=str(fiction.uid), session=session
        )
        assert still_exists is not None

    @pytest.mark.asyncio
    async def test_remove_tag_from_book_not_attached_is_noop(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Noop Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        await tag_service.add_tags_to_book(
            book_uid=str(book.uid),
            tag_data=TagAdd(tags=[TagCreate(name="fiction")]),
            session=session,
        )
        other = await tag_service.create_tag(
            tag_data=TagCreate(name="unattached"), session=session
        )

        result = await tag_service.remove_tag_from_book(
            book_uid=str(book.uid), tag_uid=str(other.uid), session=session
        )

        assert len(result.tags) == 1

    @pytest.mark.asyncio
    async def test_remove_tag_from_book_missing_tag_is_noop(self, session, test_user):
        book_service = BookService()
        book = await book_service.create_book(
            book_data=BookCreate(
                title="Noop Tag Book",
                author="Author",
                publisher="Pub",
                page_count=100,
                language="English",
                published_date="2024-01-01",
            ),
            user_uid=test_user.uid,
            session=session,
        )
        tag_service = TagService()
        await tag_service.add_tags_to_book(
            book_uid=str(book.uid),
            tag_data=TagAdd(tags=[TagCreate(name="fiction")]),
            session=session,
        )

        result = await tag_service.remove_tag_from_book(
            book_uid=str(book.uid), tag_uid=str(uuid.uuid4()), session=session
        )

        assert len(result.tags) == 1

    @pytest.mark.asyncio
    async def test_remove_tag_from_book_not_found(self, session):
        tag_service = TagService()
        with pytest.raises(BookNotFound):
            await tag_service.remove_tag_from_book(
                book_uid=str(uuid.uuid4()),
                tag_uid=str(uuid.uuid4()),
                session=session,
            )
