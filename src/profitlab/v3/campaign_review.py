"""Terminal-only authoring of a G6b ledger case from one sealed campaign run."""
import hashlib
import json

from .contracts import CampaignReview, DevelopmentCase, DevelopmentCohort, DevelopmentConfiguration
from .development_ledger import DevelopmentLedgerService


class CampaignReviewService:
    """Validate immutable reviewer input, then use the existing pure G6b scorer."""

    @staticmethod
    def cohort_id(review: CampaignReview) -> str:
        return 'development-cohort-' + review.review_id.removeprefix('campaign-review-')

    @staticmethod
    def _configuration_id(campaign) -> str:
        payload = json.dumps(campaign.configuration.model_dump(mode='json'), sort_keys=True)
        return 'campaign-' + hashlib.sha256(payload.encode()).hexdigest()[:16]

    @classmethod
    def submit(cls, review: CampaignReview, repository):
        run = repository.campaign_run(review.campaign_run_id)
        if run.campaign_id != review.campaign_id or run.experiment_id != review.experiment_id:
            raise ValueError('Review does not match its campaign run and sealed experiment.')
        if run.status != 'sealed':
            raise ValueError('Ground truth may attach only after a campaign run is sealed.')
        campaign = repository.campaign(review.campaign_id)
        inspection = repository.inspection(review.experiment_id)
        manifest = inspection['manifest']
        if manifest.finished_at is None or manifest.frontier_state == 'active':
            raise ValueError('Ground truth may attach only after the terminal manifest is persisted.')
        if review.question != campaign.question or review.question != manifest.question:
            raise ValueError('Review question does not match the sealed campaign experiment.')
        # DevelopmentLedgerService remains the single deterministic range/scoring
        # authority; this adapter makes a campaign review equivalent to its CLI input.
        cohort = DevelopmentCohort(
            cohort_id=cls.cohort_id(review), configuration_id=cls._configuration_id(campaign),
            configuration=DevelopmentConfiguration(application_revision=manifest.application_revision,
                model=manifest.model, prompt_version=manifest.prompt_version, budgets=manifest.budgets),
            cases=[DevelopmentCase(case_id=review.review_id, experiment_id=review.experiment_id,
                question=review.question, ground_truth_ranges=review.ground_truth_ranges,
                answer_support=review.answer_support, ambiguity_handling=review.ambiguity_handling,
                notes=review.notes)], created_at=review.created_at)
        report = DevelopmentLedgerService.score(cohort, repository)
        repository.save_campaign_review(review)
        repository.save_development_ledger_report(report)
        return report
