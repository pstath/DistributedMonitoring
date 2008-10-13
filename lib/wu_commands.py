import time
import re
import sre_constants

from twisted.words.xish import domish
from twisted.web import client
from sqlalchemy.orm import exc

import models

all_commands={}

def __register(cls):
    c=cls()
    all_commands[c.name]=c

class CountingFile(object):
    """A file-like object that just counts what's written to it."""
    def __init__(self):
        self.written=0
    def write(self, b):
        self.written += len(b)
    def close(self):
        pass
    def open(self):
        pass
    def read(self):
        return None

class BaseCommand(object):
    """Base class for command processors."""

    def __init__(self, name, help=None, extended_help=None):
        self.name=name
        self.help=help
        self.__extended_help=extended_help

    def extended_help(self):
        if self.__extended_help:
            return self.__extended_help
        else:
            return self.help

    def __call__(self, user, prot, args, session):
        raise NotImplementedError()

class StatusCommand(BaseCommand):

    def __init__(self):
        super(StatusCommand, self).__init__('status', 'Check your status.')

    def __call__(self, user, prot, args, session):
        rv=[]
        rv.append("Jid:  %s" % user.jid)
        rv.append("Jabber status:  %s" % user.status)
        rv.append("Whatsup status:  %s"
            % {True: 'Active', False: 'Inactive'}[user.active])
        rv.append("You are currently watching %d URLs." % len(user.watches))
        prot.send_plain(user.jid, "\n".join(rv))

__register(StatusCommand)

class GetCommand(BaseCommand):

    def __init__(self):
        super(GetCommand, self).__init__('get', 'Get a web page.')

    def __call__(self, user, prot, args, session):
        if args:
            start=time.time()
            cf = CountingFile()
            def onSuccess(value):
                prot.send_plain(user.jid, "Got %d bytes in %.2fs" %
                    (cf.written, (time.time() - start)))
            client.downloadPage(args, cf).addCallbacks(
                callback=onSuccess,
                errback=lambda error:(prot.send_plain(
                    user.jid, "Error getting the page: %s (%s)"
                    % (error.getErrorMessage(), dir(error)))))
        else:
            prot.send_plain(user.jid, "I need a URL to fetch.")

__register(GetCommand)

class HelpCommand(BaseCommand):

    def __init__(self):
        super(HelpCommand, self).__init__('help', 'You need help.')

    def __call__(self, user, prot, args, session):
        rv=[]
        if args:
            c=all_commands.get(args.strip().lower(), None)
            if c:
                rv.append("Help for %s:\n" % c.name)
                rv.append(c.extended_help())
            else:
                rv.append("Unknown command %s." % args)
        else:
            for k in sorted(all_commands.keys()):
                rv.append('%s\t%s' % (k, all_commands[k].help))
        prot.send_plain(user.jid, "\n".join(rv))

__register(HelpCommand)

class WatchCommand(BaseCommand):

    def __init__(self):
        super(WatchCommand, self).__init__('watch', 'Start watching a page.')

    def __call__(self, user, prot, args, session):
        w=models.Watch()
        w.url=args
        w.user=user
        user.watches.append(w)
        prot.send_plain(user.jid, "Started watching %s" % w.url)

__register(WatchCommand)

class UnwatchCommand(BaseCommand):

    def __init__(self):
        super(UnwatchCommand, self).__init__('unwatch', 'Stop watching a page.')

    def __call__(self, user, prot, args, session):
        try:
            watch=session.query(models.Watch).filter_by(
                url=args).filter_by(user_id=user.id).one()
            session.delete(watch)
            prot.send_plain(user.jid, "Stopped watching %s" % watch.url)
        except exc.NoResultFound:
            prot.send_plain(user.jid, "Cannot find watch for %s" % args)

__register(UnwatchCommand)

class WatchingCommand(BaseCommand):
    def __init__(self):
        super(WatchingCommand, self).__init__('watching', 'List your watches.')

    def __call__(self, user, prot, args, session):
        watches=[]
        rv=[("You are watching %d URLs:" % len(user.watches))]
        h={True: 'enabled', False: 'disabled'}
        for w in user.watches:
            watches.append("%s %s - (%s -- last=%s)" % (w.status_emoticon(),
                w.url, h[w.active], `w.status`))
        rv += sorted(watches)
        prot.send_plain(user.jid, "\n".join(rv))

__register(WatchingCommand)

class InspectCommand(BaseCommand):
    def __init__(self):
        super(InspectCommand, self).__init__('inspect', 'Inspect a watch.')

    def __call__(self, user, prot, args, session):
        try:
            w=session.query(models.Watch).filter_by(
                url=args).filter_by(user_id=user.id).one()
            rv=[]
            rv.append("Status for %s: %s"
                % (w.url, {True: 'enabled', False: 'disabled'}[w.active]))
            if w.is_quiet():
                rv.append("Alerts are quiet until %s" % str(w.quiet_until))
            rv.append("Last update:  %s" % str(w.last_update))
            if w.patterns:
                for p in w.patterns:
                    rv.append("\t%s %s" % ({True: '+', False: '-'}[p.positive],
                        p.regex))
            else:
                rv.append("No match patterns configured.")
            prot.send_plain(user.jid, "\n".join(rv))
        except exc.NoResultFound:
            prot.send_plain(user.jid, "Cannot find watch for %s" % args)

__register(InspectCommand)

class MatchCommand(BaseCommand):
    def __init__(self):
        super(MatchCommand, self).__init__('match', 'Configure a match for a URL')

    def __call__(self, user, prot, args, session):
        try:
            url, regex=args.split(' ', 1)
            re.compile(regex) # Check the regex
            w=session.query(models.Watch).filter_by(
                url=url).filter_by(user_id=user.id).one()
            m=models.Pattern()
            m.positive=True
            m.regex=regex
            w.patterns.append(m)
            prot.send_plain(user.jid, "Added pattern.")
        except exc.NoResultFound:
            prot.send_plain(user.jid, "Cannot find watch for %s" % args)
        except sre_constants.error, e:
            prot.send_plain(user.jid, "Error configuring pattern:  %s" % e.message)

__register(MatchCommand)
