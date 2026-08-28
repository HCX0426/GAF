"""Skill market backend tests.

Covers:
- SkillMarketItem / SkillMarketReview model creation
- SkillMarketViewSet endpoints: list, retrieve, publish, import, review, my_published
- Permission checks (authentication required)
- Edge cases: duplicate publish, invalid rating, import name conflict
"""

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User
from skills.models import SkillDefinition, SkillMarketItem, SkillMarketReview


def _unwrap(resp):
    """适配 unified_response 信封。优先取 resp.data['data'], 降级到 resp.data 兼容裸响应。"""
    data = resp.data
    if (isinstance(data, dict) and 'data' in data
            and 'code' in data and 'message' in data):
        return data['data']
    return data


def _get_results(resp):
    """适配信封 + 分页。先解信封, 再取分页 results 字段。"""
    data = _unwrap(resp)
    if isinstance(data, dict) and 'results' in data:
        return data['results']
    return data


class SkillMarketTestBase(TestCase):
    """Base class with common fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='market_admin',
            password='admin123456',
            role=User.Role.ADMIN,
        )
        cls.viewer = User.objects.create_user(
            username='market_viewer',
            password='viewer123456',
            role=User.Role.VIEWER,
        )
        cls.skill1 = SkillDefinition.objects.create(
            name='test_skill_1',
            description='Test skill for market',
            yaml_content='name: test_skill_1\nsteps: []',
            version='1.0',
            applicable_scenarios=['testing'],
        )
        cls.skill2 = SkillDefinition.objects.create(
            name='test_skill_2',
            description='Another test skill',
            yaml_content='name: test_skill_2\nsteps: []',
            version='2.0',
            applicable_scenarios=['demo'],
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)


class TestSkillMarketItemModel(SkillMarketTestBase):
    """SkillMarketItem model tests."""

    def test_create_market_item(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1,
            publisher=self.admin,
            title='My Skill',
            description='A great skill',
            tags=['automation', 'testing'],
        )
        self.assertEqual(item.title, 'My Skill')
        self.assertEqual(item.publisher, self.admin)
        self.assertEqual(item.status, SkillMarketItem.StatusChoices.PENDING)
        self.assertEqual(item.download_count, 0)
        self.assertEqual(item.rating_avg, 0.0)
        self.assertEqual(item.tags, ['automation', 'testing'])

    def test_status_choices(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1,
            publisher=self.admin,
            title='Test',
        )
        self.assertEqual(item.status, 'pending')
        item.status = SkillMarketItem.StatusChoices.APPROVED
        item.save()
        self.assertEqual(item.status, 'approved')

    def test_str_representation(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1,
            publisher=self.admin,
            title='My Skill',
            version='2.0',
        )
        self.assertIn('My Skill', str(item))
        self.assertIn('2.0', str(item))


class TestSkillMarketReviewModel(SkillMarketTestBase):
    """SkillMarketReview model tests."""

    def test_create_review(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1,
            publisher=self.admin,
            title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        review = SkillMarketReview.objects.create(
            item=item,
            user=self.viewer,
            rating=5,
            comment='Excellent',
        )
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.user, self.viewer)

    def test_unique_together_item_user(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1,
            publisher=self.admin,
            title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        SkillMarketReview.objects.create(
            item=item, user=self.viewer, rating=5,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            SkillMarketReview.objects.create(
                item=item, user=self.viewer, rating=3,
            )


class TestSkillMarketListRetrieve(SkillMarketTestBase):
    """List and retrieve endpoints."""

    def test_list_only_approved(self):
        SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Approved',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        SkillMarketItem.objects.create(
            skill=self.skill2, publisher=self.admin, title='Pending',
            status=SkillMarketItem.StatusChoices.PENDING,
        )
        response = self.client.get('/api/v2/skills/market/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Approved')

    def test_list_empty(self):
        response = self.client.get('/api/v2/skills/market/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_approved(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        response = self.client.get(f'/api/v2/skills/market/{item.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(_unwrap(response)['title'], 'Test')

    def test_retrieve_includes_skill_fields(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        response = self.client.get(f'/api/v2/skills/market/{item.id}/')
        body = _unwrap(response)
        self.assertEqual(body['skill_name'], 'test_skill_1')
        self.assertEqual(body['skill_version'], '1.0')
        self.assertIn('skill_yaml_content', body)

    def test_authentication_required(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v2/skills/market/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class TestSkillMarketPublish(SkillMarketTestBase):
    """Publish endpoint."""

    def test_publish_success(self):
        response = self.client.post('/api/v2/skills/market/publish/', {
            'skill': self.skill1.id,
            'title': 'Published Skill',
            'description': 'My description',
            'tags': ['automation'],
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        body = _unwrap(response)
        self.assertEqual(body['title'], 'Published Skill')
        self.assertEqual(body['status'], 'pending')
        self.assertEqual(body['publisher_name'], 'market_admin')

    def test_publish_duplicate_skill(self):
        SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='First',
        )
        response = self.client.post('/api/v2/skills/market/publish/', {
            'skill': self.skill1.id,
            'title': 'Second',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_nonexistent_skill(self):
        # PrimaryKeyRelatedField validates existence and returns 400 (DRF standard).
        response = self.client.post('/api/v2/skills/market/publish/', {
            'skill': 99999,
            'title': 'Ghost',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_publish_missing_title(self):
        response = self.client.post('/api/v2/skills/market/publish/', {
            'skill': self.skill1.id,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class TestSkillMarketImport(SkillMarketTestBase):
    """Import endpoint."""

    def test_import_success(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        initial_count = SkillDefinition.objects.count()
        response = self.client.post(f'/api/v2/skills/market/{item.id}/import/', format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SkillDefinition.objects.count(), initial_count + 1)
        item.refresh_from_db()
        self.assertEqual(item.download_count, 1)

    def test_import_pending_item_fails(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.PENDING,
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/import/', format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_import_name_conflict_resolution(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        # Pre-create a skill with the expected import name
        expected_name = f'test_skill_1_imported_{self.admin.id}'
        SkillDefinition.objects.create(
            name=expected_name,
            description='conflict',
            yaml_content='name: conflict',
            version='1.0',
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/import/', format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Should have appended _1 to avoid conflict
        new_name = _unwrap(response)['skill_name']
        self.assertNotEqual(new_name, expected_name)


class TestSkillMarketReview(SkillMarketTestBase):
    """Review endpoint."""

    def test_review_success(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 5,
            'comment': 'Great skill!',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        item.refresh_from_db()
        self.assertEqual(item.rating_avg, 5.0)
        self.assertEqual(item.rating_count, 1)

    def test_review_updates_existing(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 3, 'comment': 'ok',
        }, format='json')
        response = self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 5, 'comment': 'updated',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item.refresh_from_db()
        self.assertEqual(item.rating_count, 1)
        self.assertEqual(item.rating_avg, 5.0)

    def test_review_invalid_rating(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 6,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_missing_rating(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'comment': 'no rating',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_pending_item_fails(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.PENDING,
        )
        response = self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 5,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_review_multiple_users(self):
        item = SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Test',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 4, 'comment': 'admin rating',
        }, format='json')
        self.client.force_authenticate(user=self.viewer)
        self.client.post(f'/api/v2/skills/market/{item.id}/review/', {
            'rating': 5, 'comment': 'viewer rating',
        }, format='json')
        item.refresh_from_db()
        self.assertEqual(item.rating_count, 2)
        self.assertEqual(item.rating_avg, 4.5)


class TestSkillMarketMyPublished(SkillMarketTestBase):
    """My published endpoint."""

    def test_my_published_returns_own_items(self):
        SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Admin Skill',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        SkillMarketItem.objects.create(
            skill=self.skill2, publisher=self.viewer, title='Viewer Skill',
            status=SkillMarketItem.StatusChoices.PENDING,
        )
        response = self.client.get('/api/v2/skills/market/my-published/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], 'Admin Skill')

    def test_my_published_includes_all_statuses(self):
        SkillMarketItem.objects.create(
            skill=self.skill1, publisher=self.admin, title='Approved',
            status=SkillMarketItem.StatusChoices.APPROVED,
        )
        SkillMarketItem.objects.create(
            skill=self.skill2, publisher=self.admin, title='Pending',
            status=SkillMarketItem.StatusChoices.PENDING,
        )
        response = self.client.get('/api/v2/skills/market/my-published/')
        results = _get_results(response)
        self.assertEqual(len(results), 2)

    def test_my_published_empty(self):
        response = self.client.get('/api/v2/skills/market/my-published/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = _get_results(response)
        self.assertEqual(len(results), 0)
