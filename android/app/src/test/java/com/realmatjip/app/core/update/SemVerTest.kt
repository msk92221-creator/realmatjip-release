package com.realmatjip.app.core.update

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Test

class SemVerTest {

    @Test
    fun `v 접두사와 3세그먼트 파싱`() {
        val v = SemVer.parse("v1.2.3")
        assertEquals(1, v.major)
        assertEquals(2, v.minor)
        assertEquals(3, v.patch)
        assertTrue(v.preRelease.isEmpty())
    }

    @Test
    fun `pre-release 파싱`() {
        val v = SemVer.parse("0.2.0-phase2")
        assertEquals(listOf("phase2"), v.preRelease)
        assertTrue(v.isPreRelease)
    }

    @Test
    fun `세그먼트 누락은 0으로`() {
        val v = SemVer.parse("2.1")
        assertEquals(SemVer(2, 1, 0), v)
    }

    @Test
    fun `정식 릴리스가 pre-release보다 크다`() {
        assertTrue(SemVer.parse("0.3.0") > SemVer.parse("0.3.0-rc1"))
        assertTrue(SemVer.parse("0.2.0") < SemVer.parse("0.2.0-phase2").let { SemVer.parse("0.2.1") })
    }

    @Test
    fun `같은 버전 pre-release끼리 식별자 비교`() {
        assertTrue(SemVer.parse("1.0.0-alpha.2") > SemVer.parse("1.0.0-alpha.1"))
        assertTrue(SemVer.parse("1.0.0-beta") > SemVer.parse("1.0.0-alpha"))
        // 숫자 식별자가 영숫자보다 낮다 (SemVer 규칙 11)
        assertTrue(SemVer.parse("1.0.0-alpha") > SemVer.parse("1.0.0-1"))
    }

    @Test
    fun `major-minor-patch 우선 비교`() {
        assertTrue(SemVer.parse("1.0.0") > SemVer.parse("0.9.9"))
        assertTrue(SemVer.parse("0.10.0") > SemVer.parse("0.9.0"))
    }

    @Test
    fun `parseOrNull - 잘못된 값은 null`() {
        assertNull(SemVer.parseOrNull(null))
        assertNull(SemVer.parseOrNull(""))
        assertNull(SemVer.parseOrNull("abc"))
        assertNull(SemVer.parseOrNull("1.2.3.4"))
        assertEquals(SemVer(1, 2, 3), SemVer.parseOrNull("v1.2.3"))
    }

    @Test
    fun `앱 버전 형식 지원`() {
        // 현재 앱 버전과 릴리즈 태그 비교 시나리오
        assertFalse(SemVer.parse("0.2.0-phase2") >= SemVer.parse("0.3.0"))
        assertTrue(SemVer.parse("0.3.0") >= SemVer.parse("0.2.0-phase2"))
    }
}
