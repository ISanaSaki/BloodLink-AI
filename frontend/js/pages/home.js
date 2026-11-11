import "../ui.js";

const track = document.querySelector("[data-story-track]");
const progress = document.querySelector("[data-story-progress]");
const prev = document.querySelector("[data-story-prev]");
const next = document.querySelector("[data-story-next]");

if (track) {
  const step = () => {
    const card = track.querySelector(".story-card");
    return card ? card.getBoundingClientRect().width + 18 : 320;
  };

  const updateProgress = () => {
    if (!progress) return;
    const max = track.scrollWidth - track.clientWidth;
    const ratio = max > 0 ? Math.min(1, Math.abs(track.scrollLeft) / max) : 0;
    const rail = progress.parentElement.clientWidth;
    const bar = Math.max(42, (track.clientWidth / track.scrollWidth) * rail);
    progress.style.width = `${bar}px`;
    progress.style.transform = `translateX(${(-ratio * (rail - bar)).toFixed(1)}px)`;
  };

  prev?.addEventListener("click", () => track.scrollBy({ left: step(), behavior: "smooth" }));
  next?.addEventListener("click", () => track.scrollBy({ left: -step(), behavior: "smooth" }));
  track.addEventListener("scroll", updateProgress, { passive: true });
  window.addEventListener("resize", updateProgress);
  updateProgress();
}

/* Scrollspy for the landing navigation */
const navLinks = [...document.querySelectorAll(".nav-links .nav-link")];
const homeLink = navLinks.find((link) => link.getAttribute("href") === "index.html");
const sections = navLinks
  .filter((link) => link.getAttribute("href").startsWith("#"))
  .map((link) => ({ link, section: document.querySelector(link.getAttribute("href")) }))
  .filter((item) => item.section);

const setActive = (activeLink) => {
  navLinks.forEach((link) => {
    const active = link === activeLink;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
};

if (sections.length) {
  const spy = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const match = sections.find((item) => item.section === entry.target);
        if (match) setActive(match.link);
      });
    },
    { rootMargin: "-38% 0px -52% 0px", threshold: 0 },
  );
  sections.forEach(({ section }) => spy.observe(section));

  window.addEventListener(
    "scroll",
    () => {
      if (window.scrollY < 120) setActive(homeLink);
    },
    { passive: true },
  );
}
