from django.contrib import admin
from .models import RankingRun, RankedCandidate, SystemConfig, LocationTier, DegreeWeight, TierWeight


@admin.register(RankingRun)
class RankingRunAdmin(admin.ModelAdmin):
    list_display = ["id", "job_title", "total_candidates", "avg_score", "duration_sec", "created_at", "status"]
    list_filter = ["status"]
    readonly_fields = ["created_at"]


@admin.register(RankedCandidate)
class RankedCandidateAdmin(admin.ModelAdmin):
    list_display = ["rank", "candidate_id", "score", "reasoning", "run"]
    list_filter = ["run"]
    search_fields = ["candidate_id", "reasoning"]
    ordering = ["run", "rank"]


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    list_display = ["id", "skills_weight", "title_career_weight", "experience_weight", "education_weight", "signals_weight"]

@admin.register(LocationTier)
class LocationTierAdmin(admin.ModelAdmin):
    list_display = ["city_name", "tier"]
    list_filter = ["tier"]
    search_fields = ["city_name"]

@admin.register(DegreeWeight)
class DegreeWeightAdmin(admin.ModelAdmin):
    list_display = ["degree_key", "weight"]
    search_fields = ["degree_key"]

@admin.register(TierWeight)
class TierWeightAdmin(admin.ModelAdmin):
    list_display = ["tier_key", "weight"]
    search_fields = ["tier_key"]
