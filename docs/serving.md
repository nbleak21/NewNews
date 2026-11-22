# Serving the Feed

Overcast and Pocket Casts fetch feeds from their own servers, so the feed must be reachable from the public internet. A Tailscale-only address will not work.

The plan is to serve the `build/` folder as a static directory, with a long random token in the path so the URL cannot be guessed:

```
https://<machine>.<tailnet>.ts.net/<token>/feed.xml
```

Treat the URL like a password — anyone with the URL can subscribe and listen.

## Tailscale Funnel

Tailscale Funnel is the recommended option for most users. It exposes a port on your machine to the public internet through Tailscale's infrastructure.

### Setup Steps

1. **Install Tailscale** on your Mac (if not already installed):
   ```bash
   brew install --cask tailscale
   # or download from https://tailscale.com/download
   ```

2. **Start Tailscale** and log in:
   ```bash
   tailscale up
   ```

3. **Serve the `build/` folder** on a local port (e.g. 8080). The simplest way
   is Python's built-in server (or any static file server of your choice):
   ```bash
   cd /path/to/NewNews/build
   python3 -m http.server 8080
   ```

4. **Expose that local port with Funnel.** Funnel's public listener is always
   HTTPS on port 443; you hand it the *local* port to proxy, so there is no
   public `:8080`. Run it in the background so it survives logout and reboot:
   ```bash
   tailscale funnel --bg 8080
   ```
   Stop it with `tailscale funnel --bg 8080 off`, or `tailscale funnel reset`.

5. **Find your public URL**:
   ```bash
   tailscale funnel status
   ```
   It prints your public address as `https://<machine>.<tailnet>.ts.net` — the
   MagicDNS name (not an IP). The feed is then at
   `https://<machine>.<tailnet>.ts.net/<token>/feed.xml`.

6. **Configure NewNews**:
   - Set `public_base_url` in `config/sources.yaml` to that HTTPS base, e.g.
     `https://<machine>.<tailnet>.ts.net` (no port, no token)
   - Set `NEWNEWS_FEED_TOKEN` in `.env` to your random token
   - The final feed URL is `<public_base_url>/<token>/feed.xml`

### Rotating the Token

If you suspect the feed URL has been exposed, rotate the token:

1. Generate a new token:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Update `NEWNEWS_FEED_TOKEN` in `.env`

3. The old URL will stop working; subscribers must be given the new URL

4. Old feed items remain in the SQLite database and will be re-published at the new URL

### Troubleshooting

- **Connection refused**: Make sure Funnel is running for that local port (`tailscale funnel --bg <port>`) and the static server is up
- **404 on feed.xml**: Check that the static server is running and serving the correct directory
- **Can't reach from outside**: Verify Tailscale is connected (`tailscale status`) and Funnel is active (`tailscale funnel status`)

## Cloudflare Alternatives

If Tailscale Funnel doesn't meet your needs, here are Cloudflare options:

### Cloudflare Tunnel

Pros:
- Uses Cloudflare's edge network for better performance and DDoS protection
- Can serve over HTTPS without managing certificates
- Access controls and IP restrictions available

Cons:
- Requires running `cloudflared` daemon on your Mac
- Slightly more complex setup than Funnel

Basic setup:
1. Install `cloudflared`: `brew install cloudflared`
2. Authenticate: `cloudflared tunnel login`
3. Create a tunnel: `cloudflared tunnel create newnews`
4. Configure tunnel to proxy to your local server
5. Create a DNS record pointing to the tunnel

### Cloudflare R2 + Pages

Pros:
- Fully serverless; no need to keep your Mac running
- Free tier: 10 GB-month storage plus generous Class A/B operation quotas; **egress (data transfer out) is free and unmetered** — R2's headline feature
- Pages handles caching and CDN automatically

Cons:
- Requires rebuilding and redeploying for each feed update
- More complex CI/CD pipeline needed

Basic setup:
1. Store `feed.xml` in an R2 bucket
2. Expose the bucket publicly — make it a public bucket with a **custom domain** (simplest for one file), or front it with a Worker/Pages Function that has an R2 binding. (Pages cannot read an R2 bucket directly.)
3. Set up a custom domain with Cloudflare
4. Update the build process to upload `feed.xml` to R2 after generation

## Comparison

| Feature | Tailscale Funnel | Cloudflare Tunnel | Cloudflare R2 + Pages |
|---------|-----------------|-------------------|----------------------|
| Mac must run | Yes (always on) | Yes (runs cloudflared) | No |
| Setup complexity | Low | Medium | High |
| Cost | Free | Free tier available | Free tier (10 GB storage/mo, free egress) |
| SSL/TLS | Automatic | Automatic | Automatic |
| DDoS protection | Basic | Full Cloudflare | Full Cloudflare |
| Best for | Personal use, simple setup | Users already on Cloudflare | Fully serverless, no Mac needed |

## Subscribing

Once the feed is served:

1. In Overcast, tap **+** (Add Podcast), then **Add URL**
2. Paste the full feed URL, including the token
3. Create a Smart Playlist for CarPlay (New Playlist → Smart Playlist → include only this podcast → show unplayed → sort oldest to newest)
