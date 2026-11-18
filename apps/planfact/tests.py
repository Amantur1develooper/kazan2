from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.estimates.models import Estimate, EstimateItem, EstimateSection
from apps.projects.models import Block, ResidentialComplex
from .models import (AsmDocument, AsmItem, AvrDocument, BlockAccess, BlockFloorConfig,
                     DocumentMove, FloorCategoryAssignment, WorkCategory)


class DocumentMoveTests(TestCase):
    """Перенос АСМ/АВР на другой этаж / вид работ / блок при ошибке ввода."""

    @classmethod
    def setUpTestData(cls):
        rc = ResidentialComplex.objects.create(name='ЖК Тест')
        cls.block_a = Block.objects.create(residential_complex=rc, name='А')   # без конфига: 16 этажей
        cls.block_b = Block.objects.create(residential_complex=rc, name='Б')
        cls.block_c = Block.objects.create(residential_complex=rc, name='В')   # строителю недоступен
        BlockFloorConfig.objects.create(block=cls.block_b, total_floors=5, underground_floors=1)  # -1, 1..4
        cls.masonry = WorkCategory.objects.create(name='Кладка', scope='floor')
        cls.plaster = WorkCategory.objects.create(name='Штукатурка', scope='floor')
        cls.admin = User.objects.create_user('admin', is_staff=True)
        cls.builder = User.objects.create_user('builder')
        BlockAccess.objects.create(user=cls.builder, block=cls.block_a)
        BlockAccess.objects.create(user=cls.builder, block=cls.block_b)

    def setUp(self):
        self.asm = AsmDocument.objects.create(
            block=self.block_a, floor_number=3, category=self.masonry,
            doc_number='7', doc_date=date(2026, 11, 1), created_by=self.builder,
        )
        self.asm_item = AsmItem.objects.create(document=self.asm, name='Кирпич', unit='шт',
                                               quantity=100, unit_price=5)

    def move(self, user, doc, kind='asm', **target):
        self.client.force_login(user)
        return self.client.post(reverse(f'{kind}_move', args=[doc.pk]), {
            'target_block': target.get('block', doc.block_id),
            'target_floor': target.get('floor', doc.floor_number),
            'target_category': target.get('category', doc.category_id),
        })

    def assertPlace(self, doc, block, floor, category=None):
        doc.refresh_from_db()
        self.assertEqual((doc.block_id, doc.floor_number), (block.pk, floor))
        if category is not None:
            self.assertEqual(doc.category_id, category.pk)

    def test_builder_moves_to_another_floor_and_it_is_logged(self):
        r = self.move(self.builder, self.asm, floor=5)
        self.assertRedirects(r, reverse('asm_edit', args=[self.asm.pk]), fetch_redirect_response=False)
        self.assertPlace(self.asm, self.block_a, 5)
        log = DocumentMove.objects.get(doc_type='asm', doc_id=self.asm.pk)
        self.assertEqual(log.from_place, 'ЖК Тест / Блок А / Этаж 3 / Кладка')
        self.assertEqual(log.to_place, 'ЖК Тест / Блок А / Этаж 5 / Кладка')
        self.assertEqual((log.from_block, log.to_block, log.moved_by), (self.block_a, self.block_a, self.builder))
        self.assertFalse(log.was_accepted)

    def test_builder_cannot_move_into_block_without_access(self):
        self.move(self.builder, self.asm, block=self.block_c.pk)
        self.assertPlace(self.asm, self.block_a, 3)
        self.assertFalse(DocumentMove.objects.exists())

    def test_accepted_document_can_be_moved_only_by_admin(self):
        AsmDocument.objects.filter(pk=self.asm.pk).update(is_accepted=True)
        self.move(self.builder, self.asm, floor=4)
        self.assertPlace(self.asm, self.block_a, 3)
        self.move(self.admin, self.asm, floor=4)
        self.assertPlace(self.asm, self.block_a, 4)
        self.assertTrue(DocumentMove.objects.get().was_accepted)

    def test_floor_must_exist_in_target_block(self):
        self.move(self.admin, self.asm, block=self.block_b.pk, floor=9)
        self.assertPlace(self.asm, self.block_a, 3)
        self.move(self.admin, self.asm, block=self.block_b.pk, floor=-1)
        self.assertPlace(self.asm, self.block_b, -1)

    def test_category_must_be_enabled_on_target_floor(self):
        FloorCategoryAssignment.objects.create(block=self.block_a, floor_number=6, category=self.plaster)
        self.move(self.admin, self.asm, floor=6)                      # «Кладка» на 6 этаже не включена
        self.assertPlace(self.asm, self.block_a, 3, self.masonry)
        self.move(self.admin, self.asm, floor=6, category=self.plaster.pk)
        self.assertPlace(self.asm, self.block_a, 6, self.plaster)

    def test_bad_input_and_same_place_change_nothing(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('asm_move', args=[self.asm.pk]), {'target_block': 'x'})
        self.move(self.admin, self.asm)                               # то же место
        self.client.get(reverse('asm_move', args=[self.asm.pk]))      # GET ничего не делает
        self.assertPlace(self.asm, self.block_a, 3, self.masonry)
        self.assertFalse(DocumentMove.objects.exists())

    def test_estimate_links_follow_document_into_another_block(self):
        def estimate_item(blk, code, name):
            estimate, _ = Estimate.objects.get_or_create(block=blk)
            section, _ = EstimateSection.objects.get_or_create(estimate=estimate, name='Материалы')
            return EstimateItem.objects.create(section=section, code=code, name=name)

        src = estimate_item(self.block_a, '1.1', 'Кирпич М150')
        dst = estimate_item(self.block_b, '1.1', 'Кирпич М150')
        estimate_item(self.block_b, '1.2', 'Цемент')
        missing = estimate_item(self.block_a, '9.9', 'Нет в смете блока Б')
        self.asm_item.estimate_item = src
        self.asm_item.save()
        orphan = AsmItem.objects.create(document=self.asm, name='Сетка', unit='шт', quantity=1,
                                        unit_price=1, estimate_item=missing)

        self.move(self.admin, self.asm, block=self.block_b.pk, floor=2)
        self.assertPlace(self.asm, self.block_b, 2)
        self.asm_item.refresh_from_db()
        orphan.refresh_from_db()
        self.assertEqual(self.asm_item.estimate_item_id, dst.pk)     # та же позиция в смете блока Б
        self.assertIsNone(orphan.estimate_item_id)                    # пары нет — привязка снята
        log = DocumentMove.objects.get()
        self.assertEqual((log.links_moved, log.links_cleared), (1, 1))

    def test_avr_can_be_moved_too(self):
        avr = AvrDocument.objects.create(block=self.block_a, floor_number=2, category=self.plaster,
                                         doc_date=date(2026, 11, 2))
        r = self.move(self.builder, avr, kind='avr', block=self.block_b.pk, floor=1)
        self.assertRedirects(r, reverse('avr_edit', args=[avr.pk]), fetch_redirect_response=False)
        self.assertPlace(avr, self.block_b, 1)
        self.assertEqual(DocumentMove.objects.get().doc_type, 'avr')

    def test_edit_pages_show_move_button_and_history(self):
        self.move(self.builder, self.asm, floor=4)
        r = self.client.get(reverse('asm_edit', args=[self.asm.pk]))
        self.assertContains(r, 'id="moveDocModal"')
        self.assertContains(r, 'История переносов')
        self.assertContains(r, 'ЖК Тест / Блок А / Этаж 3 / Кладка')

        AsmDocument.objects.filter(pk=self.asm.pk).update(is_accepted=True)
        r = self.client.get(reverse('asm_edit', args=[self.asm.pk]))
        self.assertNotContains(r, 'id="moveDocModal"')                # строителю принятый не перенести
        self.client.force_login(self.admin)
        r = self.client.get(reverse('asm_edit', args=[self.asm.pk]))
        self.assertContains(r, 'id="moveDocModal"')

        avr = AvrDocument.objects.create(block=self.block_a, floor_number=2, category=self.plaster,
                                         doc_date=date(2026, 11, 2))
        r = self.client.get(reverse('avr_edit', args=[avr.pk]))
        self.assertContains(r, 'id="moveDocModal"')
