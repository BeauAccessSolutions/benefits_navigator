"""
Sitemap configuration for VA Benefits Navigator.

Provides XML sitemaps for search engine optimization.
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from examprep.models import ExamGuidance, GlossaryTerm
from appeals.models import AppealGuidance


class StaticViewSitemap(Sitemap):
    """Sitemap for static pages."""

    priority = 0.8
    changefreq = "weekly"

    def items(self):
        return [
            "home",
            "examprep:guide_list",
            "examprep:glossary_list",
            "examprep:rating_calculator",
            "examprep:smc_calculator",
            "examprep:tdiu_calculator",
            "examprep:secondary_conditions_hub",
            "appeals:home",
            "appeals:decision_tree",
        ]

    def location(self, item):
        return reverse(item)


class ExamGuideSitemap(Sitemap):
    """Sitemap for C&P exam preparation guides."""

    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return ExamGuidance.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("examprep:guide_detail", kwargs={"slug": obj.slug})


class GlossaryTermSitemap(Sitemap):
    """Sitemap for VA glossary terms."""

    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return GlossaryTerm.objects.all()

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("examprep:glossary_detail", kwargs={"pk": obj.pk})


class AppealGuidanceSitemap(Sitemap):
    """Sitemap for appeals guidance pages."""

    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return AppealGuidance.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at

    def location(self, obj):
        return reverse("appeals:guidance_detail", kwargs={"slug": obj.slug})


class SecondaryConditionSitemap(Sitemap):
    """Sitemap for secondary conditions pages."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        # Known condition slugs from the secondary conditions hub
        return [
            "ptsd",
            "tbi",
            "back-condition",
            "knee-condition",
            "diabetes",
            "sleep-apnea",
            "hypertension",
            "tinnitus",
        ]

    def location(self, item):
        return reverse(
            "examprep:secondary_condition_detail", kwargs={"condition_slug": item}
        )


# Dictionary of all sitemaps for URL configuration
sitemaps = {
    "static": StaticViewSitemap,
    "exam-guides": ExamGuideSitemap,
    "glossary": GlossaryTermSitemap,
    "appeals": AppealGuidanceSitemap,
    "secondary-conditions": SecondaryConditionSitemap,
}
