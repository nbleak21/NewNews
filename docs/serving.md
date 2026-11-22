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

3. **Enable Funnel** for the port you'll serve on (e.g., 8080):
   ```bash
   tailscale funnel 8080 on
   ```

4. **Serve the build folder** on that port. The simplest way is with Python's built-in server:
   ```bash
   cd /path/to/NewNews/build
   python3 -m http.server 8080
   ```

   Or use any static file server of your choice.

5. **Find your Tailscale hostname**:
   ```bash
   tailscale ip -4
   ```
   Your funnel URL will be `http://<ip>.zip.ts.net:8080/<token>/feed.xml` (or use your custom tailnet domain if configured).

6. **Configure NewNews**:
   - Set `public_base_url` in `config/sources.yaml` to your funnel URL base (e.g., `http://<ip>.zip.ts.net:8080`)
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

- **Connection refused**: Make sure `tailscale funnel <port> on` is enabled
- **404 on feed.xml**: Check that the static server is running and serving the correct directory
- **Can't reach from outside**: Verify Tailscale is connected (`tailscale status`) and funnel is enabled

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
- Free tier includes 10GB storage and 10GB/month egress
- Pages handles caching and CDN automatically

Cons:
- Requires rebuilding and redeploying for each feed update
- More complex CI/CD pipeline needed

Basic setup:
1. Store `feed.xml` in an R2 bucket
2. Configure Pages to serve from the bucket (or use a CI/CD workflow to deploy)
3. Set up a custom domain with Cloudflare
4. Update the build process to upload `feed.xml` to R2 after generation

## Comparison

| Feature | Tailscale Funnel | Cloudflare Tunnel | Cloudflare R2 + Pages |
|---------|-----------------|-------------------|----------------------|
| Mac must run | Yes (always on) | Yes (runs cloudflared) | No |
| Setup complexity | Low | Medium | High |
| Cost | Free | Free tier available | Free tier (10GB/mo) |
| SSL/TLS | Automatic | Automatic | Automatic |
| DDoS protection | Basic | Full Cloudflare | Full Cloudflare |
| Best for | Personal use, simple setup | Users already on Cloudflare | Fully serverless, no Mac needed |

## Subscribing

Once the feed is served:

1. In Overcast, tap **+** (Add Podcast), then **Add URL**
2. Paste the full feed URL, including the token
3. Create a Smart Playlist for CarPlay (New Playlist → Smart Playlist → include only this podcast → show unplayed → sort oldest to newest)
