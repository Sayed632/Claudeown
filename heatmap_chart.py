"""
heatmap_chart.py

Generates a simple color-graded "heat map" strip image for a list of
top stocks (ticker + % return), and sends it directly to Telegram as a
photo - no external hosting needed, since Telegram's own sendPhoto
endpoint accepts the image bytes directly.

Reusable across any scanner that wants a visual alongside its text
message (currently wired into Steady Climber; can be reused by Top
Gainers, Penny Stock, etc. later the same way).
"""
import io
import requests
import matplotlib
matplotlib.use("Agg")  # no display backend needed - headless GitHub Actions runner
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.cm as cm
import matplotlib.colors as mcolors


def generate_heatmap_image(stocks: list, title: str, value_key: str = "trend_return_pct",
                            label_key: str = "ticker") -> bytes:
    """
    stocks: list of dicts, each with at least `label_key` and `value_key`.
    Returns PNG image bytes (in memory, not saved to disk).
    """
    if not stocks:
        return None

    n = len(stocks)
    values = [s[value_key] for s in stocks]
    vmin, vmax = min(values), max(values)
    # Guard against all-identical values (would divide by zero in normalization)
    if vmax == vmin:
        vmax = vmin + 1

    cmap = cm.get_cmap("Greens")
    # Sequential (not diverging) colormap: every stock shown already passed
    # strict quality filters, so "weakest of the top 5" is still a genuine
    # winner - a red-yellow-green scale would misleadingly paint it as bad.
    # Padding the normalization range below vmin keeps even the lowest bar
    # a visible mid-green rather than washing out to near-white.
    norm = mcolors.Normalize(vmin=vmin - (vmax - vmin) * 0.6, vmax=vmax)

    fig, ax = plt.subplots(figsize=(min(2.2 * n, 12), 3))
    cell_width = 1.0

    for i, stock in enumerate(stocks):
        value = stock[value_key]
        color = cmap(norm(value))
        rect = patches.Rectangle((i * cell_width, 0), cell_width * 0.94, 1, facecolor=color, edgecolor="white")
        ax.add_patch(rect)

        label = stock[label_key].replace(".NS", "")
        ax.text(
            i * cell_width + cell_width * 0.47, 0.62, label,
            ha="center", va="center", fontsize=11, fontweight="bold", color="black",
        )
        ax.text(
            i * cell_width + cell_width * 0.47, 0.30, f"{value:+.1f}%",
            ha="center", va="center", fontsize=13, fontweight="bold", color="black",
        )

    ax.set_xlim(0, n * cell_width)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def send_telegram_photo(image_bytes: bytes, caption: str, telegram_token: str, chat_id: str) -> bool:
    if not image_bytes:
        print("No image bytes to send.")
        return False
    if not telegram_token or not chat_id:
        print("ERROR: telegram_token or chat_id not provided to send_telegram_photo.")
        return False

    url = f"https://api.telegram.org/bot{telegram_token}/sendPhoto"
    try:
        resp = requests.post(
            url,
            data={"chat_id": chat_id, "caption": caption},
            files={"photo": ("heatmap.png", image_bytes, "image/png")},
            timeout=30,
        )
        if resp.status_code != 200:
            print(f"Telegram photo send failed: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"Telegram photo send exception: {e}")
        return False
