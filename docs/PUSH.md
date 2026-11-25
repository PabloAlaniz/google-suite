# Push notifications

Instead of polling, Google can tell you when something changed. The
notification never carries the change itself, only "this mailbox / calendar /
Drive changed": you then ask the API for the delta with the token you kept.
Every service follows the same three steps:

1. **Watch**: ask Google to notify you, and keep the starting point it returns.
2. **Receive**: verify the notification and answer 2xx quickly.
3. **Sync**: fetch what changed since the starting point, and keep the new one.

| Service | Watch | Delivered through | What changed |
|---|---|---|---|
| Gmail | `gmail.watch(topic)` | A Pub/Sub topic | `gmail.history(history_id)` |
| Calendar | `calendar.watch(address, token)` | POST to your HTTPS URL | `calendar.sync(sync_token)` |
| Drive | `drive.watch_changes(address, token)` | POST to your HTTPS URL | `drive.changes(page_token)` |

Every method exists on the async clients too (`AsyncGmail`, `AsyncCalendar`,
`AsyncDrive`).

## Gmail

Gmail publishes to a [Pub/Sub](https://cloud.google.com/pubsub/docs) topic.
Create the topic, let `gmail-api-push@system.gserviceaccount.com` publish to
it, and add a subscription (push to your URL, or pull).

```python
from gsuite_gmail import Gmail

gmail = Gmail(auth)
watch = gmail.watch("projects/my-project/topics/gmail", label_ids=["INBOX"])
history_id = watch.history_id          # keep it

# on each notification
delta = gmail.history(history_id)      # .added, .deleted, .labels_changed
history_id = delta.history_id
```

Gmail stops publishing at `watch.expiration`, about a week later. Call
`watch` again before then; once a day is the usual choice. `gmail.stop_watch()`
ends it.

## Calendar

```python
from gsuite_calendar import Calendar

calendar = Calendar(auth)
sync_token = calendar.sync().sync_token                      # the starting point
channel = calendar.watch("https://example.com/webhooks/calendar", token=SECRET)

# on each notification
delta = calendar.sync(sync_token)      # .changed, .cancelled
sync_token = delta.sync_token
```

## Drive

```python
from gsuite_drive import Drive

drive = Drive(auth)
page_token = drive.get_start_page_token()
channel = drive.watch_changes("https://example.com/webhooks/drive", token=SECRET, page_token=page_token)

# on each notification
delta = drive.changes(page_token)      # .changed (files as they are now), .removed (IDs)
page_token = delta.page_token
```

## Channels expire

Calendar and Drive return a `Channel`. Google doesn't renew it: before
`channel.expiration`, watch again (a new channel) and stop the old one with
`stop_channel(channel)`. Keep `channel.id` and `channel.resource_id`, which is
all `stop_channel(id, resource_id)` needs. For a few minutes both channels
notify, so the receiver has to tolerate duplicates.

## Verifying what you receive

Notifications aren't signed. What proves they come from Google:

- **Calendar and Drive** send the `token` you passed to `watch` back in the
  `X-Goog-Channel-Token` header. Compare it in constant time and reject
  anything else. `X-Goog-Channel-ID` plus `X-Goog-Message-Number` identify a
  notification, to process each one once.
- **Gmail (Pub/Sub push)**: put a secret in the subscription's push URL
  (`?token=...`) and check it the same way; `message.messageId` in the body
  identifies the notification. Pub/Sub can also attach an OIDC token.

Answer 2xx only after the delta is safely processed (or queued): on a 5xx
Google retries, which is what you want when processing failed. And always
treat the notification as a signal: fetch the change from the API, don't trust
the request for data.
