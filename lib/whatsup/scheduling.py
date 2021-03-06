import re
import datetime

import models
import config

from twisted.web import client
from twisted.internet import defer

class CheckSites(object):

    def __init__(self, client):
        self.client = client

    @models.wants_session
    def __call__(self, session):
        ds = defer.DeferredSemaphore(tokens=config.BATCH_CONCURRENCY)
        for watch in models.Watch.todo(session, config.WATCH_FREQ):
            ds.run(self.__urlCheck, watch.id, watch.url)

    def __urlCheck(self, watch_id, url):
        return client.getPage(str(url), timeout=10).addCallbacks(
            callback=lambda page: self.onSuccess(watch_id, page),
            errback=lambda err: self.onError(watch_id, err))

    def __updateDb(self, watch, status, session):
        watch.status=status
        watch.last_update = datetime.datetime.now()
        session.commit()

    def _check_patterns(self, body, watch):
        rv=200
        failed_pattern=None
        for p in watch.patterns:
            r=re.compile(p.regex)
            if r.search(body):
                if not p.positive:
                    rv = -1
                    failed_pattern=p.regex
            else:
                if p.positive:
                    rv = -1
                    failed_pattern=p.regex
        return rv, failed_pattern

    @models.wants_session
    def onSuccess(self, watch_id, page, session):
        print "Success fetching %d: %d bytes" % (watch_id, len(page))
        watch=session.query(models.Watch).filter_by(id=watch_id).one()
        status, pattern = self._check_patterns(page, watch)
        print "Pattern status of %s: %d" % (watch.url, status)
        if status == 200:
            if status != watch.status and not watch.is_quiet():
                self.client.send_plain(watch.user.jid,
                    ":) Status of %s changed from %s to %d"
                    % (watch.url, `watch.status`, status))
        else:
            self._reportError(watch, status, "Pattern failed: %s" % pattern)
        self.__updateDb(watch, status, session)

    def _reportError(self, watch, status, err_msg):
        msg = ":( Error in %s: %d - %s" % (watch.url, status, err_msg)
        if watch.is_quiet():
            print "User is quiet, not sending", msg
        else:
            self.client.send_plain(watch.user.jid, msg)

    @models.wants_session
    def onError(self, watch_id, error, session):
        print "Error fetching %d: %s" % (watch_id, error)
        watch=session.query(models.Watch).filter_by(id=watch_id).one()
        try:
            status=int(error.getErrorMessage()[0:3])
        except:
            status=-1
        self._reportError(watch, status, error.getErrorMessage())
        self.__updateDb(watch, status, session)
