# Bedtime Manhwa website (local build, not published)

A small static site for our recaps and articles, meant for GitHub Pages (free) under the CEO's GitHub account, in a new
repo such as `bedtime-manhwa-site`. **Nothing is published yet**: no repo, no push. Going live is publishing, so it waits
for the Director's QC and the CEO's own go.

## Build and preview

```
python site/build.py            # public site -> site/docs/
python site/serve.py            # http://127.0.0.1:8801/bedtime-manhwa-site/
python site/build.py --drafts   # drafts too -> site/preview_drafts/ (serve with: python site/serve.py --drafts)
```

Python 3 with Jinja2 (already installed). No other packages; the markdown converter is built in.

## Content

- `site.json`: the site name, tagline, `base_url` (every link gets its path) and the YouTube channel. A custom domain
  later is a one-line change here (it costs money, so it's the CEO's call).
- `content/series/<slug>.json`: one per series: tagline, description, credits, official links, and the parts.
  A part is `"status": "public"` with its `youtube_id`, or `"upcoming"` with **no id**.
- `content/articles/<slug>/index.md`: published articles (front matter + markdown, credited panels beside it).
  The first three came from Yohan's drafts in `shared/content_manager/drafts/`; from now on this folder can be the
  master copy, and our site is the canonical home of each article.
- `content/drafts/`: drafts. Git-ignored, because they may name private uploads.
- `root/`: files copied byte for byte to the site root on every build. It holds the Google Search Console
  verification file (`google3c44219caaa6c826.html`); keep it for good, or the site drops out of Search Console.

## Built-in rules

- Only public parts get a video, thumbnail or id. The build **stops** if any YouTube id in the output isn't a public
  part's, so a private upload can't leak.
- "Coming soon" part pages are `noindex` and left out of the sitemap until the video is public.
- Every series and part page carries the credits and the official links.
- Nothing is deleted: files an earlier build wrote but this one didn't are listed for moving to `_HOLDING`.

## SEO

Per page: title, meta description, canonical URL, Open Graph and Twitter cards (a public part uses its YouTube
thumbnail, an article its first credited panel, otherwise the brand card), JSON-LD (WebSite, Article, BreadcrumbList,
VideoObject once a part's `published` date is filled in), `sitemap.xml`, `robots.txt`, clean URLs such as
`/nano-machine/part-1/`, and a 404 page. Videos load as a thumbnail and only fetch the player (youtube-nocookie) on tap.

## Going live (after the go-ahead)

Create the repo, commit everything except the git-ignored folders, and in the repo's Settings → Pages choose
"Deploy from a branch", `main`, folder `/docs`. Then submit `sitemap.xml` in Google Search Console (the CEO's account).
