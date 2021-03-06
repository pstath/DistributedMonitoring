import datetime

from sqlalchemy import *
from sqlalchemy.orm import sessionmaker, mapper, relation, backref, exc

from whatsup import config

_engine = create_engine(config.CONF.get('general', 'db'))

_metadata = MetaData()

Session = sessionmaker()
Session.configure(bind=_engine)

def wants_session(orig):
    def f(*args):
        session = Session()
        try:
            return orig(*args + (session,))
        finally:
            session.close()
    return f

class Quietable(object):
    def is_quiet(self):
        """Is this user quiet?"""
        rv=False
        if self.quiet_until:
            rv = self.quiet_until > datetime.datetime.now()
        return rv

class User(Quietable):

    @staticmethod
    def by_jid(jid, session=None):
        s=session
        if not s:
            s=Session()
        try:
            return session.query(User).filter_by(jid=jid).one()
        finally:
            if not session:
                s.close()

    @staticmethod
    def update_status(jid, status, session=None):
        """Find or create a user by jid and set the user's status"""
        s=session
        if not s:
            s = Session()
        try:
            u = None
            if not status:
                status="online"
            try:
                u=User.by_jid(jid, s)
            except exc.NoResultFound, e:
                u=User()
                u.jid=jid

            u.status=status
            s.add(u)
            s.commit()
            return u
        finally:
            if not session:
                s.close()

class Watch(Quietable):

    @staticmethod
    def todo(session, timeout=10):
        """Get the items to do."""
        ID_QUERY="""select w.*
          from watches w join users on (users.id == w.user_id)
          where
            users.active is not null
            and users.active = :uactive
            and users.status not in ('dnd', 'offline', 'unavailable')
            and w.active = :wactive
            and ( w.last_update is null or w.last_update < :last_update)
          limit 50
          """
        then=datetime.datetime.now() - datetime.timedelta(minutes=timeout)
        return session.query(Watch).from_statement(ID_QUERY).params(
            uactive=True, wactive=True, last_update=then)

    def status_emoticon(self):
        if not self.active:
            rv=":-#"
        elif self.status == 200:
            rv=":)"
        else:
            rv=":("
        return rv

    def is_quiet(self):
        return super(Watch, self).is_quiet() or self.user.is_quiet()

class Pattern(object):
    pass

_users_table = Table('users', _metadata,
    Column('id', Integer, primary_key=True, index=True, unique=True),
    Column('jid', String(128), index=True, unique=True),
    Column('active', Boolean, default=True),
    Column('status', String(50)),
    Column('quiet_until', DateTime))

_watches_table = Table('watches', _metadata,
    Column('id', Integer, primary_key=True, index=True, unique=True),
    Column('user_id', Integer, ForeignKey('users.id'), index=True),
    Column('url', String(1024)),
    Column('status', Integer),
    Column('active', Boolean, default=True),
    Column('quiet_until', DateTime),
    Column('last_update', DateTime),
)
Index('idx_watches_user_url', _watches_table.c.user_id, _watches_table.c.url,
    unique=True)

_patterns_table = Table('patterns', _metadata,
    Column('id', Integer, primary_key=True, index=True),
    Column('watch_id', Integer, ForeignKey('watches.id')),
    Column('positive', Boolean),
    Column('regex', String(1024))
)

mapper(User, _users_table, properties={
    'watches': relation(Watch, cascade="all, delete, delete-orphan")
    })
mapper(Watch, _watches_table, properties={
    'user': relation(User),
    'patterns': relation(Pattern, cascade="all, delete, delete-orphan")
    })
mapper(Pattern, _patterns_table, properties={
    'watch': relation(Watch)
    })
