from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import Article
from content.research_guides import RESEARCH_GUIDES
from content.reviewed_guides import ARTICLES


class Command(BaseCommand):
    help = "Seed or update /learn/ articles (idempotent)."

    def handle(self, *args, **opts):
        now = timezone.now()
        for data in ARTICLES + RESEARCH_GUIDES:
            defaults = {key: data[key] for key in ("title", "meta_description", "body")}
            article, created = Article.objects.get_or_create(
                slug=data["slug"], defaults={**defaults, "published_at": now}
            )
            changed = [key for key, value in defaults.items() if getattr(article, key) != value]
            if not created and changed:
                for key in changed:
                    setattr(article, key, defaults[key])
                article.save(update_fields=[*changed, "updated_at"])
            self.stdout.write(
                self.style.SUCCESS(f"{'created' if created else ('updated' if changed else 'unchanged')}: {article.slug}")
            )
