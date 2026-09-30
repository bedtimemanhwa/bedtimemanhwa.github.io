// Tap a video thumbnail to load the player there (youtube-nocookie). Without JavaScript the link opens YouTube.
document.addEventListener("click", function (e) {
  var a = e.target.closest ? e.target.closest("a.yt[data-yt]") : null;
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  var f = document.createElement("iframe");
  f.src = "https://www.youtube-nocookie.com/embed/" + a.getAttribute("data-yt") + "?autoplay=1&rel=0";
  f.title = a.getAttribute("aria-label") || "YouTube video";
  f.allow = "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
  f.allowFullscreen = true;
  var box = document.createElement("div");
  box.className = "yt";
  box.appendChild(f);
  a.replaceWith(box);
});
// Close the Series menu when you tap elsewhere
document.addEventListener("click", function (e) {
  document.querySelectorAll("details.menu[open]").forEach(function (d) { if (!d.contains(e.target)) d.removeAttribute("open"); });
});
