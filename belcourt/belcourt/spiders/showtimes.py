import scrapy
from datetime import datetime
from zoneinfo import ZoneInfo
from belcourt.items import BelcourtItem

#the Belcourt is in Nashville; "today" means today in Central time
BELCOURT_TZ = ZoneInfo("America/Chicago")


def clean_text(fragments):
    """Join scraped text fragments into one string with tidy whitespace.

    Scrapy's //text() returns every text node separately, including the
    newlines between tags, e.g. ['\\n', 'A Red Carpet Evening', '\\n'].
    Collapsing all runs of whitespace to single spaces keeps those stray
    newlines from turning into blank lines on the rendered image.

    Fragments are concatenated with '' (not ' ') so a title split across
    tags, like 'ANORA (' + '35mm' + ')', stays 'ANORA (35mm)'.
    """
    return ' '.join(''.join(fragments).split())


class ShowtimesSpider(scrapy.Spider):
    name = 'showtimes'
    allowed_domains = ['belcourt.org']
    start_urls = ['http://belcourt.org/']

    def parse(self, response):
        
        #initiate object that will store results
        belcourt = BelcourtItem()

        #record the scrape time in the Belcourt's own time zone, not the
        #machine's. The GitHub runner's clock is UTC, so after ~6-7pm Central
        #a plain datetime.now() would already be "tomorrow". The format is
        #unchanged; belcourt_generate_image.py reads it back as Central time.
        belcourt["currenttime"] = datetime.now(BELCOURT_TZ).strftime("%Y-%m-%d %H:%M:%S")

        #capture date
        belcourt["date"] = response.xpath('//div[@class="day today"]//h4[@class="widget-subtitle"]//text()').getall()
        
        #belcourt["showtimes"]


        j = 0
        dict_shows_all = {}

        #cycle through shows and capture showtimes
        for div_day in response.xpath('//div[@class="day today"]//ul[@class="day-event-list"]/li'): 

            print(f"------Show {j+1}:")

            #show_name = div_day.xpath('.//a[@class="day-event-list__title"]//text() | .//span[@class="day-event-list__title"]//text()').getall()
            show_name = div_day.xpath('.//*[@class="day-event-list__title"]//text()').getall()
            print(show_name)

            showtimes = div_day.xpath('.//ul[@class="day-event-list__time-list"]/li/a//text()').getall()
            
            #remove empty strings from showtimes
            showtimes = [time for time in showtimes if time.strip()]

            print(showtimes)

            #if showtimes is empty, look for a description (e.g. "No films are
            #screening today..." when the theater is closed for an event).
            #It is stored in its own "description" field, not in "showtimes",
            #so the image generator can tell the two apart and format the
            #description differently (with a " — " separator, not as times).
            description = ''
            if not showtimes:
                description = clean_text(div_day.xpath('.//*[@class="day-event-list__description"]//text()').getall())

            dict_shows_all.update({j: {
                "show": [clean_text(show_name)], #in case multiple show names are captured, join them into one string in a one element list
                "showtimes": showtimes,
                "description": description
            }})

            j = j + 1
        
        
        belcourt["shows"] = dict_shows_all

        print("------Final output:")
        print(belcourt)

        return belcourt

#Run in terminal from inside spiders directory (uv finds pyproject.toml in the
#repo root and uses its locked environment):
# cd belcourt/belcourt/spiders
# uv run scrapy runspider showtimes.py
# uv run scrapy runspider showtimes.py -O ../../output_showtimes.json