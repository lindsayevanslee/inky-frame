import scrapy
from datetime import datetime
from belcourt.items import BelcourtItem

class ShowtimesSpider(scrapy.Spider):
    name = 'showtimes'
    allowed_domains = ['belcourt.org']
    start_urls = ['http://belcourt.org/']

    def parse(self, response):
        
        #initiate object that will store results
        belcourt = BelcourtItem()

        belcourt["currenttime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        #capture date
        belcourt["date"] = response.xpath('//div[@class="day today"]//h4[@class="widget-subtitle"]//text()').getall()
        
        #belcourt["showtimes"]


        j = 0
        dict_shows_all = {}

        #cycle through shows and capture showtimes
        for div_day in response.xpath('//div[@class="day today"]//ul[@class="day-event-list"]/li'): 

            show_name = div_day.xpath('.//a[@class="day-event-list__title"]/text()').getall()

            showtimes = div_day.xpath('.//ul[@class="day-event-list__time-list"]/li/a/text()').getall()

            dict_shows_all.update({j: {
                "show": show_name,
                "showtimes": showtimes
            }})

            j = j + 1
        
        
        belcourt["shows"] = dict_shows_all

        return belcourt

#Run in termainal from inside spiders directory: 
# cd belcourt/belcourt/spiders
# scrapy runspider showtimes.py
# scrapy runspider showtimes.py -o ../../output_showtimes.json