from django.db import models
import json


class RankingRun(models.Model):
    """Stores metadata about each ranking run."""
    created_at = models.DateTimeField(auto_now_add=True)
    job_title = models.CharField(max_length=200, default="AI/ML Engineer")
    job_description = models.TextField(blank=True)
    total_candidates = models.IntegerField(default=0)
    duration_sec = models.FloatField(default=0)
    avg_score = models.FloatField(default=0)
    max_score = models.FloatField(default=0)
    status = models.CharField(max_length=50, default="completed")
    submission_csv = models.FileField(upload_to="submissions/", blank=True, null=True)
    stats_json = models.TextField(blank=True, default="{}")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run #{self.pk} — {self.job_title} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    def get_stats(self):
        try:
            return json.loads(self.stats_json)
        except Exception:
            return {}

    def set_stats(self, stats_dict):
        self.stats_json = json.dumps(stats_dict)


class RankedCandidate(models.Model):
    """Top-100 ranked candidates from a run."""
    run = models.ForeignKey(RankingRun, on_delete=models.CASCADE, related_name="candidates")
    rank = models.IntegerField()
    candidate_id = models.CharField(max_length=20)
    score = models.FloatField()
    raw_score = models.FloatField(default=0)
    reasoning = models.TextField()
    profile_json = models.TextField(default="{}")
    components_json = models.TextField(default="{}")
    signals_json = models.TextField(default="{}")

    class Meta:
        ordering = ["rank"]

    def get_profile(self):
        try:
            return json.loads(self.profile_json)
        except Exception:
            return {}

    def get_components(self):
        try:
            return json.loads(self.components_json)
        except Exception:
            return {}

    def get_signals(self):
        try:
            return json.loads(self.signals_json)
        except Exception:
            return {}


class SystemConfig(models.Model):
    """Singleton model for global scoring weights."""
    skills_weight = models.FloatField(default=0.40)
    title_career_weight = models.FloatField(default=0.25)
    experience_weight = models.FloatField(default=0.15)
    education_weight = models.FloatField(default=0.10)
    signals_weight = models.FloatField(default=0.10)
    
    class Meta:
        verbose_name = "System Configuration"
        verbose_name_plural = "System Configuration"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class LocationTier(models.Model):
    """Stores cities and their tier to score alignment dynamically."""
    city_name = models.CharField(max_length=100, unique=True)
    tier = models.IntegerField(choices=[(1, 'Tier 1 (High Priority)'), (2, 'Tier 2 (Medium Priority)'), (3, 'Tier 3 (Low Priority)')])
    
    def __str__(self):
        return f"{self.city_name} (Tier {self.tier})"


class DegreeWeight(models.Model):
    """Maps degree strings to their score weight [0, 1]."""
    degree_key = models.CharField(max_length=50, unique=True, help_text="e.g. phd, m.tech, mba")
    weight = models.FloatField()
    
    def __str__(self):
        return f"{self.degree_key}: {self.weight}"


class TierWeight(models.Model):
    """Maps institution tiers to their score weight [0, 1]."""
    tier_key = models.CharField(max_length=50, unique=True, help_text="e.g. tier_1, tier_2")
    weight = models.FloatField()
    
    def __str__(self):
        return f"{self.tier_key}: {self.weight}"
