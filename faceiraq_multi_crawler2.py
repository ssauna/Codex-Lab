#!/usr/bin/env python3
"""
faceiraq.org 멀티 섹션 크롤러
정치, 안보, 경제 섹션을 모두 수집하는 스크립트

사용법:
    python3 faceiraq_multi_crawler2.py [--hours HOURS] [--sections SECTIONS]
    
예시:
    # 모든 섹션 수집 (기본)
    python3 faceiraq_multi_crawler2.py
    
    # 특정 섹션만 수집
    python3 faceiraq_multi_crawler2.py --sections politics,security
    
    # 48시간 범위로 수집
    python3 faceiraq_multi_crawler2.py --hours 48
    
출력:
    faceiraq_politics_YYYYMMDD_HHMMSS.json/csv
    faceiraq_security_YYYYMMDD_HHMMSS.json/csv
    faceiraq_economy_YYYYMMDD_HHMMSS.json/csv
"""

import json
import time
import re
import argparse
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import csv

class FaceIraqMultiCrawler:
    # 섹션 정의
    SECTIONS = {
        'politics': {
            'name_kr': '정치',
            'name_ar': 'سياسة',
            'url': 'https://www.faceiraq.org/articles/%D8%B3%D9%8A%D8%A7%D8%B3%D8%A9'
        },
        'security': {
            'name_kr': '안보',
            'name_ar': 'أمن',
            'url': 'https://www.faceiraq.org/articles/%D8%A3%D9%85%D9%86'
        },
        'economy': {
            'name_kr': '경제',
            'name_ar': 'اقتصاد',
            'url': 'https://www.faceiraq.org/articles/%D8%A7%D9%82%D8%AA%D8%B5%D8%A7%D8%AF'
        }
    }
    
    def __init__(self, hours_limit=24, sections=None):
        """
        Args:
            hours_limit: 수집할 기사의 시간 제한 (기본 24시간)
            sections: 수집할 섹션 리스트 (None이면 모든 섹션)
        """
        self.hours_limit = hours_limit
        self.cutoff_time = datetime.utcnow() - timedelta(hours=hours_limit)
        
        # 수집할 섹션 결정
        if sections is None:
            self.target_sections = list(self.SECTIONS.keys())
        else:
            self.target_sections = [s for s in sections if s in self.SECTIONS]
        
        # Chrome 옵션 설정
        chrome_options = Options()
        chrome_options.page_load_strategy = "eager"
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--lang=ar')
        chrome_options.add_argument('--window-size=1920,1080')
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # 섹션별 결과 저장
        self.results = {}
        for section in self.target_sections:
            self.results[section] = {
                'articles': [],
                'seen_titles': set()
            }
    
    def parse_time(self, time_str):
        """
        시간 문자열을 datetime 객체로 변환
        
        지원 형식:
        1. "منذ X ساعات" (X시간 전)
        2. "منذ X دقيقة" (X분 전)
        3. "منذ ساعة واحدة" (1시간 전)
        4. "HH:MM DD-MM-YYYY" (절대 시간)
        """
        time_str = time_str.strip()
        
        # 패턴 1: "منذ X ساعات" (X시간 전)
        match = re.search(r'منذ\s+(\d+)\s+ساعات?', time_str)
        if match:
            hours_ago = int(match.group(1))
            return datetime.utcnow() - timedelta(hours=hours_ago)
        
        # 패턴 2: "منذ X دقيقة" (X분 전)
        match = re.search(r'منذ\s+(\d+)\s+دقيقة', time_str)
        if match:
            minutes_ago = int(match.group(1))
            return datetime.utcnow() - timedelta(minutes=minutes_ago)
        
        # 패턴 3: "منذ ساعة واحدة" (1시간 전)
        if 'منذ ساعة واحدة' in time_str or 'منذ ساعتين' in time_str:
            hours_ago = 1 if 'واحدة' in time_str else 2
            return datetime.utcnow() - timedelta(hours=hours_ago)
        
        # 패턴 4: "HH:MM DD-MM-YYYY" (절대 시간)
        match = re.search(r'(\d{1,2}):(\d{2})\s+(\d{1,2})-(\d{1,2})-(\d{4})', time_str)
        if match:
            hour, minute, day, month, year = map(int, match.groups())
            # 이라크 시간 (UTC+3)을 UTC로 변환
            iraq_time = datetime(year, month, day, hour, minute)
            utc_time = iraq_time - timedelta(hours=3)
            return utc_time
        
        # 파싱 실패 시 현재 시간 반환
        return datetime.utcnow()
    
    def is_within_time_limit(self, publish_date):
        """기사가 시간 제한 내에 있는지 확인"""
        return publish_date >= self.cutoff_time
    
    def crawl_section(self, section_key):
        """특정 섹션 크롤링"""
        section = self.SECTIONS[section_key]
        url = section['url']
        name_kr = section['name_kr']
        
        print(f"\n{'='*60}")
        print(f"📰 {name_kr} 섹션 크롤링 시작")
        print(f"URL: {url}")
        print(f"{'='*60}\n")
        
        self.driver.get(url)
        time.sleep(3)
        
        scroll_count = 0
        max_scrolls = 10
        old_articles_count = 0
        max_old_articles = 5
        
        while scroll_count < max_scrolls:
            # 페이지 소스 가져오기
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # v-card 찾기
            cards = soup.find_all('div', class_='v-card')
            
            for card in cards:
                try:
                    # 제목 추출
                    title_elem = card.find('p', class_='article-title')
                    if not title_elem:
                        continue
                    title = title_elem.get_text(strip=True)
                    
                    # 중복 체크
                    if title in self.results[section_key]['seen_titles']:
                        continue
                    
                    # 시간 추출
                    time_elem = card.find('div', class_='v-card-subtitle')
                    time_text = time_elem.get_text(strip=True) if time_elem else ''
                    
                    # 출처 추출
                    img_elem = card.find('img')
                    source = img_elem.get('title', 'Unknown') if img_elem else 'Unknown'
                    
                    # URL 추출
                    link_elem = card.find('a', href=True)
                    article_url = 'https://www.faceiraq.org' + link_elem['href'] if link_elem else ''
                    
                    # 시간 파싱
                    publish_date = self.parse_time(time_text)
                    
                    # 시간 제한 확인
                    if not self.is_within_time_limit(publish_date):
                        old_articles_count += 1
                        if old_articles_count >= max_old_articles:
                            print(f"✓ 24시간 이전 기사 {max_old_articles}개 발견, 크롤링 종료")
                            return
                        continue
                    
                    # 기사 정보 저장
                    article = {
                        'section': name_kr,
                        'section_key': section_key,
                        'title': title,
                        'publishDate': publish_date.isoformat() + 'Z',
                        'timeText': time_text,
                        'source': source,
                        'url': article_url
                    }
                    
                    self.results[section_key]['articles'].append(article)
                    self.results[section_key]['seen_titles'].add(title)
                    
                    print(f"✓ [{name_kr}] {title[:50]}... ({source})")
                
                except Exception as e:
                    continue
            
            # 스크롤
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            scroll_count += 1
            
            print(f"  스크롤 {scroll_count}/{max_scrolls} (수집: {len(self.results[section_key]['articles'])}개)")
        
        print(f"\n✓ {name_kr} 섹션 크롤링 완료: {len(self.results[section_key]['articles'])}개 기사")
    
    def save_results(self, section_key):
        """섹션별 결과를 JSON 및 CSV 파일로 저장"""
        articles = self.results[section_key]['articles']
        section_name = self.SECTIONS[section_key]['name_kr']
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 최신순 정렬
        articles.sort(key=lambda x: x.get('publishDate', ''), reverse=True)
        
        # JSON 저장
        json_filename = f"faceiraq_{section_key}_{timestamp}.json"
        with open(json_filename, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"✓ JSON 파일 저장: {json_filename}")
        
        # CSV 저장
        csv_filename = f"faceiraq_{section_key}_{timestamp}.csv"
        with open(csv_filename, 'w', encoding='utf-8', newline='') as f:
            if articles:
                fieldnames = ['section', 'arabic_title', 'korean_title', 'publishDate', 'timeText', 'source', 'url']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for article in articles:
                    writer.writerow({
                        'section': article.get('section', ''),
                        'arabic_title': article.get('title', ''),
                        'korean_title': '',  # GPT로 번역 필요
                        'publishDate': article.get('publishDate', ''),
                        'timeText': article.get('timeText', ''),
                        'source': article.get('source', ''),
                        'url': article.get('url', '')
                    })
        print(f"✓ CSV 파일 저장: {csv_filename}")
        
        return json_filename, csv_filename
    
    def print_summary(self):
        """수집 결과 요약 출력"""
        print(f"\n{'='*60}")
        print("📊 수집 결과 요약")
        print(f"{'='*60}\n")
        
        total_articles = 0
        for section_key in self.target_sections:
            articles = self.results[section_key]['articles']
            section_name = self.SECTIONS[section_key]['name_kr']
            count = len(articles)
            total_articles += count
            
            print(f"📰 {section_name}: {count}개")
            
            # 출처별 통계
            sources = {}
            for article in articles:
                source = article.get('source', 'Unknown')
                sources[source] = sources.get(source, 0) + 1
            
            print(f"   출처별:")
            for source, count in sorted(sources.items(), key=lambda x: x[1], reverse=True):
                print(f"   - {source}: {count}개")
            print()
        
        print(f"✅ 총 수집: {total_articles}개 기사")
        print(f"⏰ 수집 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 수집 범위: 최근 {self.hours_limit}시간\n")
    
    def run(self):
        """크롤링 실행"""
        try:
            print(f"\n🚀 faceiraq.org 멀티 섹션 크롤러 시작")
            print(f"수집 섹션: {', '.join([self.SECTIONS[s]['name_kr'] for s in self.target_sections])}")
            print(f"시간 범위: 최근 {self.hours_limit}시간\n")
            
            # 각 섹션 크롤링
            for section_key in self.target_sections:
                self.crawl_section(section_key)
            
            # 결과 저장
            print(f"\n{'='*60}")
            print("💾 결과 저장 중...")
            print(f"{'='*60}\n")
            
            for section_key in self.target_sections:
                if self.results[section_key]['articles']:
                    self.save_results(section_key)
            
            # 요약 출력
            self.print_summary()
            
        except Exception as e:
            print(f"\n❌ 오류 발생: {str(e)}")
            import traceback
            traceback.print_exc()
        
        finally:
            self.driver.quit()


def main():
    parser = argparse.ArgumentParser(description='faceiraq.org 멀티 섹션 크롤러')
    parser.add_argument('--hours', type=int, default=24,
                        help='수집할 시간 범위 (기본: 24시간)')
    parser.add_argument('--sections', type=str, default=None,
                        help='수집할 섹션 (쉼표로 구분, 예: politics,security,economy)')
    
    args = parser.parse_args()
    
    # 섹션 파싱
    sections = None
    if args.sections:
        sections = [s.strip() for s in args.sections.split(',')]
        # 유효한 섹션만 필터링
        valid_sections = list(FaceIraqMultiCrawler.SECTIONS.keys())
        sections = [s for s in sections if s in valid_sections]
        if not sections:
            print(f"❌ 유효한 섹션이 없습니다. 사용 가능한 섹션: {', '.join(valid_sections)}")
            return
    
    crawler = FaceIraqMultiCrawler(hours_limit=args.hours, sections=sections)
    crawler.run()


if __name__ == "__main__":
    main()
