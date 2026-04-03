export type NavNode = {
  title: string;
  key: string;
  href?: string;
  children?: NavNode[];
};

export const navigationTree: NavNode[] = [
  {
    title: "Home",
    key: "home",
    href: "/"
  },

  {
    title: "AI Planner",
    key: "planner",
    children: [

      {
        title: "Residential",
        key: "planner_residential",
        children: [
          {
            title: "Single Unit Housing",
            key: "single_unit_housing",
            children: [
              {
                title: "Private Residence",
                key: "private_residence",
                href: "/planner/workspace/private-residence"
              },
              {
                title: "Villa Development",
                key: "villa_development",
                href: "/planner/workspace/villa-development"
              }
            ]
          },
          {
            title: "Multi Unit Housing",
            key: "multi_unit_housing",
            children: [
              {
                title: "High Rise Residential",
                key: "high_rise_residential",
                href: "/planner/workspace/high-rise"
              },
              {
                title: "Mixed Residential",
                key: "mixed_residential",
                href: "/planner/workspace/mixed-residential"
              },
              {
                title: "Apartment Complex",
                key: "apartment_complex",
                href: "/planner/workspace/apartment-complex"
              }
            ]
          }
        ]
      },

      {
        title: "Commercial",
        key: "planner_commercial",
        children: [
          {
            title: "Office Development",
            key: "office_dev",
            children: [
              {
                title: "Office Building",
                key: "office_building",
                href: "/planner/workspace/office-building"
              },
              {
                title: "Business Park",
                key: "business_park",
                href: "/planner/workspace/business-park"
              }
            ]
          },
          {
            title: "Retail Development",
            key: "retail_dev",
            children: [
              {
                title: "Retail Mall",
                key: "retail_mall",
                href: "/planner/workspace/retail-mall"
              },
              {
                title: "Shopping Complex",
                key: "shopping_complex",
                href: "/planner/workspace/shopping-complex"
              }
            ]
          },
          {
            title: "Hospitality",
            key: "hospitality",
            children: [
              {
                title: "Hotel",
                key: "hotel",
                href: "/planner/workspace/hotel"
              },
              {
                title: "Resort",
                key: "resort",
                href: "/planner/workspace/resort"
              }
            ]
          }
        ]
      },

      {
        title: "Urban Development",
        key: "planner_urban",
        children: [
          {
            title: "City Planning",
            key: "city_planning",
            children: [
              {
                title: "City Block Planning",
                key: "city_block",
                href: "/planner/workspace/city-block"
              },
              {
                title: "Smart City Layout",
                key: "smart_city",
                href: "/planner/workspace/smart-city"
              }
            ]
          },
          {
            title: "Public Infrastructure",
            key: "public_infra",
            children: [
              {
                title: "Public Park",
                key: "park",
                href: "/planner/workspace/public-park"
              },
              {
                title: "Transit Oriented Development",
                key: "transit_dev",
                href: "/planner/workspace/transit-oriented-development"
              },
              {
                title: "Public Plaza",
                key: "public_plaza",
                href: "/planner/workspace/public-plaza"
              }
            ]
          }
        ]
      },

      {
        title: "Institutional",
        key: "planner_institutional",
        children: [
          {
            title: "Education",
            key: "education",
            children: [
              {
                title: "School Campus",
                key: "school_campus",
                href: "/planner/workspace/school-campus"
              },
              {
                title: "University Campus",
                key: "university_campus",
                href: "/planner/workspace/university-campus"
              }
            ]
          },
          {
            title: "Healthcare",
            key: "healthcare",
            children: [
              {
                title: "Hospital Layout",
                key: "hospital_layout",
                href: "/planner/workspace/hospital-layout"
              }
            ]
          }
        ]
      },

      {
        title: "Industrial",
        key: "planner_industrial",
        children: [
          {
            title: "Manufacturing",
            key: "manufacturing",
            children: [
              {
                title: "Factory Layout",
                key: "factory_layout",
                href: "/planner/workspace/factory-layout"
              }
            ]
          },
          {
            title: "Logistics",
            key: "logistics",
            children: [
              {
                title: "Warehouse Planning",
                key: "warehouse",
                href: "/planner/workspace/warehouse"
              },
              {
                title: "Logistics Park",
                key: "logistics_park",
                href: "/planner/workspace/logistics-park"
              }
            ]
          }
        ]
      }
    ]
  },

  {
    title: "AI Interior",
    key: "interior",
    children: [
      {
        title: "Residential Interior",
        key: "residential_interior",
        children: [
          {
            title: "Living Room",
            key: "living_room",
            href: "/interior/residential/living-room"
          },
          {
            title: "Bedroom",
            key: "bedroom",
            href: "/interior/residential/bedroom"
          },
          {
            title: "Kitchen",
            key: "kitchen",
            href: "/interior/residential/kitchen"
          },
          {
            title: "Bathroom",
            key: "bathroom",
            href: "/interior/residential/bathroom"
          }
        ]
      },

      {
        title: "Commercial Interior",
        key: "commercial_interior",
        children: [
          {
            title: "Office Interior",
            key: "office_interior",
            href: "/interior/commercial/office"
          },
          {
            title: "Retail Interior",
            key: "retail_interior",
            href: "/interior/commercial/retail"
          },
          {
            title: "Restaurant Interior",
            key: "restaurant_interior",
            href: "/interior/commercial/restaurant"
          }
        ]
      },

      {
        title: "Hospitality Interior",
        key: "hospitality_interior",
        children: [
          {
            title: "Hotel Interior",
            key: "hotel_interior",
            href: "/interior/hospitality/hotel"
          },
          {
            title: "Cafe Interior",
            key: "cafe_interior",
            href: "/interior/hospitality/cafe"
          },
          {
            title: "Lounge Interior",
            key: "lounge_interior",
            href: "/interior/hospitality/lounge"
          }
        ]
      }
    ]
  },

  {
    title: "Dashboard",
    key: "dashboard",
    href: "/dashboard"
  }
];