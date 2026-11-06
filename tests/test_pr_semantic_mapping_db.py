"""The store query behind semantic PR mapping (issue #54), against a REAL mongoDB.

Requires MONGO_TEST_URI like the other dbintegration tests; skipped when no MongoDB is
Reachable. A plain mongod has no mongot, so `$vectorSearch` fails here and these tests
exercise the in-memory fallback of `Store.semantic_feature_scores`. The `$vectorSearch`
branch is exercised two ways: against `VectorSearchEmulator` below (a stand-in that answers
the pipeline the way mongot does, including its "nearest 50 CHUNKS" truncation, so the
runner-up logic runs without a search engine), and against a real mongot when
MONGO_SEARCH_TEST_URI points at a replica set that runs one (skipped otherwise).
"""
import math
import os
import time
import uuid

import pytest
from bson import ObjectId
from pymongo import MongoClient

pytestmark = pytest.mark.dbintegration

MONGO_TEST_URH€ô½Ì¹•Ñ•¹Ø ‰5=9=}QMQ}UI$ˆ°€‰µ½¹½‘ˆè¼½±½…±¡½ÍĞèÈÜÀÄÜˆ¤)5=9=}MI!}QMQ}UI$€ô½Ì¹•Ñ•¹Ø ‰5=9=}MI!}QMQ}UI$ˆ°€ˆˆ¤(()ÁåÑ•ÍĞ¹™¥áÑÕÉ”¡Í½Á”ô‰µ½‘Õ±”ˆ°…ÕÑ½ÕÍ”õQÉÕ”¤)‘•˜}É•ÅÕ¥É•}µ½¹¼ ¤è(€€€€ˆˆ‰=Á•¸„Í¡½ÉĞµ±¥Ù•±¥•¹Ğ½¹±äİ¡•¸Ñ¡”µ½‘Õ±”ÌÑ•ÍÑÌ…ÑÕ…±±äÉÕ¸¸((€€€½¥¹œÑ¡”É•…¡…‰¥±¥Ñä¡•¬…Ğ¥µÁ½ÉĞÑ¥µ”€¡Ñ¡”ÁÉ•Ù¥½ÕÌÁ…ÑÑ•É¸¤½Á•¹•„(€€€5½¹½±¥•¹ĞƒŠP…¹İ…¥Ñ•Ñ¡”™Õ±°Í•ÉÙ•ÉM•±•Ñ¥½¹Q¥µ•½ÕĞƒŠP•Ù•¸İ¡•¸Ñ¡”(€€€‘‰¥¹Ñ•É…Ñ¥½¸µ…É­•Èİ…Ì‘•Í•±•Ñ•°…¹Ñ¡”±¥•¹Ğİ…Ì¹•Ù•È±½Í•¸(€€€€ˆˆˆ(€€€±¥•¹Ğ€ô9½¹”(€€€ÑÉäè(€€€€€€€±¥•¹Ğ€ô5½¹½±¥•¹Ğ¡5=9=}QMQ}UI$°Í•ÉÙ•ÉM•±•Ñ¥½¹Q¥µ•½ÕÑ5LôÄÔÀÀ¤(€€€€€€€±¥•¹Ğ¹…‘µ¥¸¹½µµ…¹ ‰Á¥¹œˆ¤(€€€•á•ÁĞá•ÁÑ¥½¸è€€Œ¹½Å„è	1ÀÀÄ(€€€€€€€ÁåÑ•ÍĞ¹Í­¥À (€€€€€€€€€€€˜‰¹¼5½¹½É•…¡…‰±”…Ğí5=9=}QMQ}UI$…Éô€¡Í•Ğ5=9=}QMQ}UI$Ñ¼ÉÕ¸€ˆ(€€€€€€€€€€€€‰‘ˆµ¥¹Ñ•É…Ñ¥½¸Ñ•ÍÑÌ¤ˆ°(€€€€€€€€€€€…±±½İ}µ½‘Õ±•}±•Ù•°õ…±Í”°(€€€€€€€€¤(€€€™¥¹…±±äè(€€€€€€€¥˜±¥•¹Ğ¥Ì¹½Ğ9½¹”è(€€€€€€€€€€€±¥•¹Ğ¹±½Í” ¤()¥µÁ½ÉĞ½Ù•É…”…Ì½Ø€€Œ¹½Å„èĞÀÈ)™É½´ÍÑ½É”¥µÁ½ÉĞMÑ½É”€€Œ¹½Å„èĞÀÈ(()Á…Ñ•ÍĞ¹™¥áÑÕÉ” ¤)‘•˜ÍÑ½É” ¤è(€€€‘‰}¹…µ”€ô˜İ…É‘•¹¥Å}Ñ•ÍÑ}íÕÕ¥¹ÕÕ¥Ğ ¤¹¡•álèÄÁuôœ(