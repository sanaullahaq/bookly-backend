import uuid

from sqlmodel import desc, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.books.service import BookService
from src.db.models import Tag
from src.errors import BookNotFound, TagAlreadyExists, TagNotFound
from src.tags.schemas import TagAdd, TagCreate

book_service = BookService()


class TagService:
    async def get_tags(self, session: AsyncSession):
        statement = select(Tag).order_by(desc(Tag.created_at))

        result = await session.exec(statement)

        return result.all()

    async def add_tags_to_book(
        self, book_uid: str, tag_data: TagAdd, session: AsyncSession
    ):
        # ------------------------------------------------------------
        # 1. Validate that the book exists in the database.
        #    get_book() internally tries uuid.UUID(str(book_uid)) and
        #    returns None if parsing fails or no row is found.
        # ------------------------------------------------------------
        book = await book_service.get_book(book_uid=book_uid, session=session)

        if not book:
            raise BookNotFound()

        # ------------------------------------------------------------
        # 2. Process each tag from the request payload.
        #    tag_data.tags is a List[TagCreate] — each item has a .name.
        #    We use a "find-or-create" pattern so the same tag name can
        #    be shared across multiple books (many-to-many).
        #
        #    Duplicates are guarded two ways because BookTag has a
        #    composite primary key (book_uid + tag_uid):
        #      - A tag already linked to this book is NOT appended again
        #        (re-appending would INSERT a duplicate BookTag row,
        #        which violates the PK and 500s on commit).
        #      - A name repeated within this request is processed once.
        #        get_tag_by_name() queries the DB, which can't see the
        #        still-unflushed inserts, so the second occurrence would
        #        otherwise create a duplicate Tag row. Adding each
        #        processed name to book_tag_names makes those repeats
        #        hit the same skip as already-attached tags.
        # ------------------------------------------------------------
        book_tag_names = {tag.name for tag in book.tags}

        for tag_item in tag_data.tags:
            # ------------------------------------------------------------
            # 2a. Skip names already attached to this book or already
            #     handled earlier in this request.
            # ------------------------------------------------------------
            if tag_item.name in book_tag_names:
                continue

            # ------------------------------------------------------------
            # 2b. Look up an existing Tag by name; create it if missing.
            #     A new Tag is NOT yet tracked by the session — appending
            #     it to a tracked parent's relationship (cascade
            #     save-update) is what INSERTs it on the next flush.
            # ------------------------------------------------------------
            tag = await self.get_tag_by_name(tag_name=tag_item.name, session=session)

            if not tag:
                tag = Tag(name=tag_item.name)

            # ------------------------------------------------------------
            # 2c. Append the Tag to the book's relationship list.
            #     SQLAlchemy tracks this append and queues a BookTag link
            #     row to INSERT on the next flush.
            # ------------------------------------------------------------
            book.tags.append(tag)
            book_tag_names.add(tag_item.name)

        # ------------------------------------------------------------
        # 3. Explicitly add the book to the session's identity map.
        #    book is already tracked (fetched via session on line 28),
        #    so this call is technically a no-op for book itself.
        #
        #    However, if any tag was newly created (section 2b) and
        #    was NOT automatically cascaded, this ensures it's tracked.
        #    In SQLModel, cascade="save-update" is the default on
        #    many-to-many relationships, so even this is redundant.
        #    Keeping it here is defensive documentation.
        # ------------------------------------------------------------
        session.add(book)

        # ------------------------------------------------------------
        # 4. Flush all pending changes to the database and commit.
        #    - Any newly created Tag rows are INSERTed.
        #    - BookTag link rows are INSERTed for each (book_uid, tag_uid).
        #    - After commit, the session clears its "expire all" flag,
        #      meaning all loaded objects are marked as expired/stale.
        # ------------------------------------------------------------
        await session.commit()

        # ------------------------------------------------------------
        # 5. Refresh the book object from the database.
        #
        #    Why this is necessary:
        #      After commit(), SQLAlchemy expires all attributes of
        #      every object in the session. If anything downstream
        #      (e.g., FastAPI response serialization) accesses
        #      book.tags, it would trigger a lazy load. In an async
        #      session, lazy loads raise MissingGreenlet because
        #      there's no greenlet context to run the query in.
        #
        #    What refresh() does:
        #      It re-queries the DB for the book's current row AND
        #      eagerly re-populates all relationship collections
        #      (including book.tags) using the configured loader
        #      strategy (lazy="selectin"). The returned book now
        #      has fully loaded, non-expired data.
        #
        #    Without refresh():
        #      Accessing book.tags in the route handler or during
        #      response serialization would raise MissingGreenlet.
        # ------------------------------------------------------------
        await session.refresh(book)

        # ------------------------------------------------------------
        # 6. Return the book with its tags eagerly loaded.
        #    FastAPI serializes this into the response_model schema.
        #    Since book.tags is already loaded, no lazy load occurs
        #    during serialization.
        # ------------------------------------------------------------
        return book

    async def remove_tag_from_book(
        self, book_uid: str, tag_uid: str, session: AsyncSession
    ):
        book = await book_service.get_book(book_uid=book_uid, session=session)

        if not book:
            raise BookNotFound()

        tag = await self.get_tag_by_uid(tag_uid=tag_uid, session=session)

        if tag and tag in book.tags:
            book.tags.remove(tag)

            await session.commit()

            await session.refresh(book)
        return book

    async def get_tag_by_name(self, tag_name: str, session: AsyncSession):
        result = await session.exec(select(Tag).where(Tag.name == tag_name))
        tag = result.one_or_none()
        return tag

    async def get_tag_by_uid(self, tag_uid: str, session: AsyncSession):
        try:
            tag_uid_obj = uuid.UUID(str(tag_uid))
        except ValueError:
            return None

        statement = select(Tag).where(Tag.uid == tag_uid_obj)
        result = await session.exec(statement)
        return result.first()

    async def create_tag(self, tag_data: TagCreate, session: AsyncSession):
        tag = await self.get_tag_by_name(tag_name=tag_data.name, session=session)
        if tag is not None:
            raise TagAlreadyExists()

        new_tag = Tag(name=tag_data.name)

        session.add(new_tag)

        await session.commit()

        return new_tag

    async def update_tag(
        self, tag_uid: str, tag_update_data: TagCreate, session: AsyncSession
    ):
        tag = await self.get_tag_by_uid(tag_uid=tag_uid, session=session)

        if tag is not None:
            tag_update_data_dict = tag_update_data.model_dump()
            for k, v in tag_update_data_dict.items():
                setattr(tag, k, v)

            await session.commit()

            await session.refresh(tag)

            return tag
        else:
            raise TagNotFound()

    async def delete_tag(self, tag_uid: str, session: AsyncSession):
        tag = await self.get_tag_by_uid(tag_uid, session)

        if not tag:
            raise TagNotFound()

        await session.delete(tag)

        await session.commit()
