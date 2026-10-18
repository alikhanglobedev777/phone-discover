import json

from django.core.management.base import BaseCommand, CommandError

from recommendations.automatic_research import research_and_save
from recommendations.research_providers import research_catalog
from recommendations.local_rank import interpret_local_request, rank_pakistan_phones
from recommendations.serializers import PakistanRecommendationSerializer


class Command(BaseCommand):
    help = "Run one live grounded phone search; optionally save sourced discoveries. Never prints credentials."

    def add_arguments(self, parser):
        parser.add_argument("message")
        parser.add_argument("--save", action="store_true")

    def handle(self, *args, **options):
        query = PakistanRecommendationSerializer(data={"message": options["message"]})
        query.is_valid(raise_exception=True)
        criteria = interpret_local_request(query.validated_data)
        result = research_and_save(criteria) if options["save"] else research_catalog(criteria)
        self.stdout.write(json.dumps({
            "status": result["status"], "notice": result["notice"], "saved": result.get("saved", {}),
            "sources": result.get("sources", []), "discovered": result.get("document", {}).get("phones", []),
            "cards": [row["device"]["slug"] for row in result.get("results", [])],
            "matching_local_count": rank_pakistan_phones(criteria)["count"] if options["save"] else None,
        }, indent=2))
        if result["status"] != "grounded_preview":
            raise CommandError("Live web research did not return grounded results; see status above.")
