#!/usr/bin/env python3
"""
Seed all educational domain banks with grade-level (K-12) knowledge.

This script populates each of the 10 main educational domain banks with
appropriate curriculum knowledge for grades K through 12.
"""

from __future__ import annotations
import sys
from pathlib import Path

# Add parent directory to path to import domain bank services
HERE = Path(__file__).resolve().parent
MAVEN_ROOT = HERE.parent
sys.path.append(str(MAVEN_ROOT))

from brains.domain_banks.math.service.math_bank import service_api as math_api
from brains.domain_banks.science.service.science_bank import service_api as science_api
from brains.domain_banks.history.service.history_bank import service_api as history_api
from brains.domain_banks.technology.service.technology_bank import service_api as technology_api
from brains.domain_banks.arts.service.arts_bank import service_api as arts_api
from brains.domain_banks.language_arts.service.language_arts_bank import service_api as language_arts_api
from brains.domain_banks.geography.service.geography_bank import service_api as geography_api
from brains.domain_banks.philosophy.service.philosophy_bank import service_api as philosophy_api
from brains.domain_banks.economics.service.economics_bank import service_api as economics_api
from brains.domain_banks.law.service.law_bank import service_api as law_api


# Define grade level knowledge for each domain
GRADE_KNOWLEDGE = {
    "math": {
        "K": "In kindergarten math, students learn to count to 100, recognize numbers 0-20, understand basic shapes (circle, square, triangle, rectangle), compare sizes (bigger/smaller), and sort objects by attributes.",
        "1": "In first grade math, students learn addition and subtraction within 20, understand place value for tens and ones, measure length using units, tell time to the hour and half-hour, and identify coins and their values.",
        "2": "In second grade math, students work with numbers up to 1000, add and subtract within 100, understand even and odd numbers, measure using standard units, work with money, and tell time to 5-minute intervals.",
        "3": "In third grade math, students multiply and divide within 100, understand fractions as parts of a whole, solve two-step word problems, measure area and perimeter, and work with time intervals and liquid volumes.",
        "4": "In fourth grade math, students work with multi-digit multiplication and division, compare and operate with fractions, understand decimal notation, convert measurements within a system, and analyze geometric shapes and angles.",
        "5": "In fifth grade math, students perform operations with multi-digit numbers and decimals to hundredths, add and subtract fractions with unlike denominators, understand volume, graph points on coordinate planes, and classify two-dimensional figures.",
        "6": "In sixth grade math, students work with ratios and proportions, divide fractions, understand negative numbers, solve equations with variables, calculate area and volume of complex shapes, and analyze statistical data.",
        "7": "In seventh grade math, students work with rational numbers including negative fractions and decimals, solve multi-step equations and inequalities, understand proportional relationships, work with probability, and analyze geometric constructions.",
        "8": "In eighth grade math, students work with integer exponents, understand functions and their graphs, solve systems of linear equations, apply the Pythagorean theorem, and work with irrational numbers and scientific notation.",
        "9": "In ninth grade math (Algebra I), students master linear equations and inequalities, understand functions in depth, work with quadratic expressions and equations, analyze exponential functions, and study polynomials and factoring.",
        "10": "In tenth grade math (Geometry), students study logical reasoning and proofs, analyze properties of triangles and polygons, work with similarity and congruence, understand circles and their properties, and study coordinate geometry and transformations.",
        "11": "In eleventh grade math (Algebra II), students study polynomial functions, rational expressions and equations, radical functions, exponential and logarithmic functions, trigonometry, and sequences and series.",
        "12": "In twelfth grade math (Pre-Calculus/Calculus), students study limits and continuity, derivatives and their applications, integration techniques, trigonometric identities, polar coordinates, and vectors."
    },
    "science": {
        "K": "In kindergarten science, students observe weather patterns and seasons, learn about plants and animals and their basic needs, explore properties of objects (color, size, texture, weight), and understand day and night cycles.",
        "1": "In first grade science, students study animal life cycles and habitats, learn about plant parts and growth, observe seasonal changes, explore properties of matter (solid, liquid, gas), and study the sun, moon, and stars.",
        "2": "In second grade science, students learn about food chains and ecosystems, study states of matter and their changes, observe force and motion, explore Earth's resources (water, soil, rocks), and understand phases of the moon.",
        "3": "In third grade science, students study adaptations in plants and animals, learn about simple machines and forces, explore the water cycle, study weather and climate, and understand magnetism and electricity basics.",
        "4": "In fourth grade science, students learn about energy transfer and forms of energy, study ecosystems and organism interactions, explore Earth's layers and plate tectonics, understand the rock cycle, and study properties of light and sound.",
        "5": "In fifth grade science, students study the structure and function of cells, learn about the solar system and space, explore properties of matter and chemical vs physical changes, understand Earth's systems (geosphere, hydrosphere, atmosphere), and study human body systems.",
        "6": "In sixth grade science, students study heredity and genetics, learn about Earth's history through fossils and rock layers, explore plate tectonics and natural disasters, understand the organization of the solar system, and study thermal energy and heat transfer.",
        "7": "In seventh grade science, students learn about cell processes (photosynthesis, respiration), study the periodic table and atomic structure, explore chemical reactions and equations, understand body systems in depth, and study electromagnetic spectrum and waves.",
        "8": "In eighth grade science, students study Newton's laws of motion and forces, learn about genetics and evolution, explore the chemistry of acids and bases, understand Earth's climate systems and factors, and study renewable and nonrenewable energy sources.",
        "9": "In ninth grade science (Biology), students study cell biology and cellular processes in depth, learn about DNA structure and protein synthesis, explore genetics including Mendelian and non-Mendelian inheritance, understand evolution and natural selection, and study ecology and environmental science.",
        "10": "In tenth grade science (Chemistry), students study atomic theory and structure, understand the periodic table and periodic trends, learn about chemical bonding (ionic, covalent, metallic), explore stoichiometry and chemical reactions, and study gases, solutions, and acids-bases.",
        "11": "In eleventh grade science (Physics), students study kinematics and dynamics, learn about work, energy, and power, explore momentum and collisions, understand waves and sound, study electricity and magnetism, and explore optics and modern physics concepts.",
        "12": "In twelfth grade science (Advanced courses), students may study advanced biology (biochemistry, molecular biology), advanced chemistry (organic chemistry, thermodynamics), advanced physics (quantum mechanics, relativity), anatomy and physiology, or environmental science at a college level."
    },
    "history": {
        "K": "In kindergarten social studies, students learn about families and community helpers, understand rules and why they matter, recognize American symbols (flag, Pledge of Allegiance), and explore concepts of past, present, and future.",
        "1": "In first grade social studies, students study families past and present, learn about community and neighborhoods, understand basic map skills and directions, explore American holidays and their meanings, and study important historical figures like George Washington.",
        "2": "In second grade social studies, students learn about American heroes and leaders, study community and citizenship responsibilities, explore urban and rural communities, understand basic economics (goods, services, needs, wants), and study American symbols and their significance.",
        "3": "In third grade social studies, students study their local community history and geography, learn about Indigenous peoples and early settlers, explore government at local and state levels, understand basic economics including resources and trade, and study important historical figures and events in their region.",
        "4": "In fourth grade social studies, students study their state's history and geography in depth, learn about Native Americans in their region, explore European exploration and colonization, understand the American Revolution, and study westward expansion and pioneer life.",
        "5": "In fifth grade social studies, students study early American history including Indigenous peoples, colonial America, the American Revolution, the Constitution and Bill of Rights, westward expansion, the Civil War, and Reconstruction.",
        "6": "In sixth grade social studies, students study ancient civilizations (Mesopotamia, Egypt, Greece, Rome), learn about world religions and their origins, explore early African, Asian, and American civilizations, understand the Middle Ages and feudalism, and study the Renaissance and Reformation.",
        "7": "In seventh grade social studies, students study world history from the Renaissance through the Age of Revolutions, learn about European exploration and colonization, explore the Enlightenment and its impact, understand the French Revolution, and study the Industrial Revolution and its global effects.",
        "8": "In eighth grade social studies, students study American history from colonization through Reconstruction in depth, learn about the Constitution and its principles, explore the Civil War and its causes and effects, understand immigration and urbanization, and study the expansion of American democracy.",
        "9": "In ninth grade social studies (World History), students study imperialism and its global impact, learn about World War I causes, events, and consequences, explore the Russian Revolution and rise of communism, understand the Great Depression globally, and study World War II and the Holocaust.",
        "10": "In tenth grade social studies (World History continued), students study the Cold War and its impact worldwide, learn about decolonization in Africa and Asia, explore the Civil Rights movement globally, understand the fall of communism, and study modern conflicts and globalization.",
        "11": "In eleventh grade social studies (U.S. History), students study American history from Reconstruction through the present, learn about Progressive Era reforms, explore America's role in both World Wars, understand the Civil Rights Movement, and study modern American politics, economy, and society.",
        "12": "In twelfth grade social studies (Government/Economics), students study the structure and function of American government (legislative, executive, judicial branches), learn about political systems and ideologies, explore civil rights and liberties, understand economic systems (capitalism, socialism), and study fiscal and monetary policy."
    },
    "technology": {
        "K": "In kindergarten technology, students learn basic computer operations (mouse, keyboard), understand digital citizenship basics (being kind online), use simple educational software and apps, explore basic coding concepts through unplugged activities, and learn to follow digital safety rules.",
        "1": "In first grade technology, students practice keyboarding skills, learn to navigate educational websites safely, use digital tools for drawing and creating, understand the difference between real and digital worlds, and explore simple cause-and-effect programming with visual blocks.",
        "2": "In second grade technology, students develop keyboarding fluency, learn to save and retrieve digital files, use word processing for simple documents, understand internet safety and privacy basics, and create simple programs using block-based coding platforms.",
        "3": "In third grade technology, students learn to use spreadsheets for simple data collection, create multimedia presentations with text and images, understand copyright and giving credit for others' work, explore debugging in programming, and practice responsible online behavior and communication.",
        "4": "In fourth grade technology, students use digital research tools effectively, create presentations with multiple media types (text, images, audio, video), understand algorithms and their role in technology, work with loops and events in programming, and learn about protecting personal information online.",
        "5": "In fifth grade technology, students develop advanced presentation skills, learn to evaluate online sources for credibility, create programs with variables and conditionals, understand how computers store and process data, and explore how technology impacts society and the environment.",
        "6": "In sixth grade technology, students learn text-based coding fundamentals, understand computer hardware and software components, create digital media projects combining multiple tools, explore internet infrastructure and how data travels, and study cybersecurity basics and protecting against threats.",
        "7": "In seventh grade technology, students learn about data structures and algorithms, explore database concepts and queries, understand networks and protocols, create interactive programs and games, and study artificial intelligence basics and its applications.",
        "8": "In eighth grade technology, students develop web design skills (HTML, CSS), learn about cloud computing and online collaboration tools, understand mobile app design principles, explore data analysis and visualization, and study ethical issues in technology including privacy and bias.",
        "9": "In ninth grade technology (Computer Science I), students learn programming fundamentals with a high-level language (Python, Java), understand object-oriented programming concepts, explore algorithms and complexity, work with data structures (arrays, lists, dictionaries), and study software development processes.",
        "10": "In tenth grade technology (Computer Science II), students advance in object-oriented programming, learn about inheritance and polymorphism, work with file I/O and data persistence, explore recursion and advanced algorithms, and study software design patterns and principles.",
        "11": "In eleventh grade technology (Advanced topics), students may study advanced data structures (trees, graphs, hash tables), learn about web development (front-end and back-end), explore mobile app development, understand database design and SQL, or study cybersecurity and encryption.",
        "12": "In twelfth grade technology (College-level CS), students may study advanced algorithms and complexity theory, learn about operating systems and computer architecture, explore artificial intelligence and machine learning, work on software engineering projects, or study specialized topics like robotics or game development."
    },
    "arts": {
        "K": "In kindergarten art, students explore basic art materials (crayons, paint, clay), learn primary colors and how to mix them, create simple drawings and paintings, practice cutting and gluing, and explore texture through various materials.",
        "1": "In first grade art, students learn secondary colors through color mixing, practice drawing basic shapes and turning them into objects, explore printmaking with simple stamps, create collages with various materials, and study famous artworks and artists.",
        "2": "In second grade art, students work with patterns and repetition in art, explore warm and cool colors, practice drawing from observation, create three-dimensional sculptures, and learn about different art styles and cultural art forms.",
        "3": "In third grade art, students study line quality and types (thick, thin, curved, straight), explore symmetry and balance in composition, practice shading techniques for depth, work with clay to create functional objects, and study art from different historical periods.",
        "4": "In fourth grade art, students learn about perspective and creating depth, explore complementary colors and color schemes, practice drawing proportions of the human figure, work with mixed media techniques, and study how art reflects culture and history.",
        "5": "In fifth grade art, students develop drawing skills including gesture and contour, study value and how light affects form, explore abstract art and expressionism, create narrative artworks that tell stories, and analyze artwork using elements and principles of design.",
        "6": "In sixth grade art, students study one-point perspective drawing, learn about positive and negative space, explore portraiture and facial proportions, work with various painting techniques, and study Renaissance art and its impact on Western art.",
        "7": "In seventh grade art, students learn two-point perspective, explore color theory in depth including tints, tones, and shades, practice still life drawing and painting, work with sculpture using various materials, and study modern art movements (Impressionism, Post-Impressionism).",
        "8": "In eighth grade art, students develop advanced drawing and painting skills, explore graphic design and typography, work with digital art tools, study composition and the rule of thirds, and analyze contemporary art and its social context.",
        "9": "In ninth grade art (Art I), students develop technical skills in multiple media, study elements and principles of design in depth, explore various art movements and styles, create portfolio pieces, and begin developing personal artistic voice and style.",
        "10": "In tenth grade art (Art II), students focus on building a cohesive portfolio, explore advanced techniques in chosen media, study art history from ancient to modern times, develop conceptual thinking in art-making, and prepare work for critique and exhibition.",
        "11": "In eleventh grade art (Art III/AP Art), students develop a concentration or theme for portfolio work, master advanced techniques in multiple media, study contemporary art theory and criticism, create sophisticated conceptual pieces, and prepare for AP Art portfolio if applicable.",
        "12": "In twelfth grade art (Advanced Art/Portfolio), students complete portfolio for college applications, explore personal artistic vision and style at advanced level, study career opportunities in art and design fields, participate in exhibitions and competitions, and may study specialized areas like animation, photography, or ceramics at depth."
    },
    "language_arts": {
        "K": "In kindergarten language arts, students learn letter recognition and letter-sound correspondence, begin to read simple words and sentences, practice writing letters and their names, develop phonemic awareness skills, and listen to and discuss stories read aloud.",
        "1": "In first grade language arts, students practice decoding skills for reading, read and comprehend grade-level texts, write simple sentences and stories, learn basic punctuation (periods, question marks, exclamation points), and expand vocabulary through reading and conversation.",
        "2": "In second grade language arts, students build reading fluency and comprehension, identify main ideas and details in texts, write narratives and informational pieces with beginning-middle-end structure, learn to use commas and apostrophes, and practice cursive writing.",
        "3": "In third grade language arts, students read chapter books and longer texts independently, distinguish between literal and non-literal language, write multi-paragraph essays with clear structure, study parts of speech (nouns, verbs, adjectives, adverbs), and conduct short research projects.",
        "4": "In fourth grade language arts, students analyze characters, settings, themes, and plots in literature, compare and contrast information from multiple texts, write opinion pieces with supporting evidence, study complex sentence structures, and expand academic vocabulary.",
        "5": "In fifth grade language arts, students analyze how authors develop points of view, summarize and synthesize information across texts, write argumentative and informational essays, study verb tenses and subject-verb agreement, and deliver oral presentations with multimedia.",
        "6": "In sixth grade language arts, students analyze literary elements (plot structure, conflict, characterization), distinguish claims from evidence in arguments, write for various purposes and audiences, study phrase and clause types, and analyze how texts are structured.",
        "7": "In seventh grade language arts, students analyze how authors develop themes, evaluate arguments and evidence critically, write analytical essays with textual evidence, study complex sentence structures and active/passive voice, and compare how different media treat the same topic.",
        "8": "In eighth grade language arts, students analyze how authors use literary devices, evaluate credibility of sources, write research papers with proper citations, study grammar including verbals and mood, and analyze seminal U.S. documents and their themes.",
        "9": "In ninth grade language arts (English I), students read world literature from various periods and cultures, analyze how authors use rhetoric and style, write literary analysis essays, study vocabulary in context, and practice effective communication and presentation skills.",
        "10": "In tenth grade language arts (English II), students read British and world literature, analyze complex themes and motifs, write argumentative and analytical essays with sophisticated structure, study advanced grammar and syntax, and explore how historical context influences literature.",
        "11": "In eleventh grade language arts (English III), students read American literature from various periods, analyze rhetorical strategies and their effects, write research papers and literary analyses, study etymology and word relationships, and prepare for standardized tests like SAT/ACT.",
        "12": "In twelfth grade language arts (English IV), students read contemporary and classic literature, synthesize information from multiple complex sources, write college-level analytical and argumentative essays, refine grammar and style, and prepare for college writing including application essays."
    },
    "geography": {
        "K": "In kindergarten geography, students learn basic directional words (up, down, left, right), understand that maps show places, identify their home address and school location, recognize land and water on simple maps, and learn about different types of weather.",
        "1": "In first grade geography, students learn cardinal directions (north, south, east, west), use simple maps to locate places, understand the difference between maps and globes, identify continents and oceans on a globe, and study different landforms (mountains, valleys, plains).",
        "2": "In second grade geography, students read maps with keys and legends, understand relative location, compare urban, suburban, and rural areas, learn about different climates and how they affect people, and study basic geography of their state and country.",
        "3": "In third grade geography, students use map scales to calculate distance, understand latitude and longitude basics, study physical and political maps, learn about natural resources and their distribution, and explore how geography affects culture and economy.",
        "4": "In fourth grade geography, students study their state's geography in detail including regions and landforms, learn to read topographic maps, understand climate zones and vegetation patterns, explore how geography influenced settlement patterns, and study major rivers, mountain ranges, and landmarks.",
        "5": "In fifth grade geography, students study geography of the United States including all regions, understand how geography influenced historical events, learn about natural disasters and their geographic causes, explore population distribution and migration patterns, and study relationships between physical and human geography.",
        "6": "In sixth grade geography, students study world geography with focus on major regions and countries, learn about plate tectonics and how mountains and earthquakes occur, understand climate patterns and factors that influence them, explore cultural geography and how environment shapes culture, and study global resources and their distribution.",
        "7": "In seventh grade geography, students analyze how geography affects economic systems, study urbanization and its environmental impacts, learn about geographic factors in political conflicts, understand ecosystems and biomes worldwide, and explore human migration patterns and their causes.",
        "8": "In eighth grade geography, students study geographic regions of the United States in depth, analyze how geography has influenced American history, learn about land use and environmental issues, understand demographic patterns and population trends, and study natural resources and energy geography.",
        "9": "In ninth grade geography (World Geography), students study regions of the world systematically (Asia, Africa, Europe, Americas, Oceania), analyze physical and human geography interactions, learn about globalization and its geographic dimensions, understand environmental issues from a geographic perspective, and study cultural diffusion and its patterns.",
        "10": "In tenth grade geography (continued), students may continue world regional studies, analyze geopolitical issues and territorial disputes, study economic geography and development patterns, learn about sustainable development and conservation, and explore GIS (Geographic Information Systems) and spatial analysis.",
        "11": "In eleventh grade, geography is often integrated with U.S. History, where students study American geographic regions and their development, analyze how geography influenced key historical events and policies, learn about westward expansion and Manifest Destiny from a geographic lens, understand regional economic differences, and study environmental history.",
        "12": "In twelfth grade, geography may be studied as an AP Human Geography course covering population and migration, cultural patterns and processes, political organization of space, agricultural and rural land use, industrialization and economic development, cities and urban land use, and contemporary geographic issues."
    },
    "philosophy": {
        "K": "In kindergarten, philosophical thinking begins with questions about fairness and sharing, understanding feelings and empathy, discussing what makes something right or wrong, exploring the concept of friendship, and thinking about what makes them happy.",
        "1": "In first grade, students begin thinking philosophically about honesty and truth, discussing what makes someone a good friend, exploring concepts of fairness in games and rules, questioning why rules exist, and considering perspective-taking (how others might feel).",
        "2": "In second grade, students think about responsibility and consequences, discuss what it means to be brave, explore concepts of kindness and helping others, question the difference between needs and wants, and consider what makes something beautiful.",
        "3": "In third grade, students explore questions about identity (who am I?), discuss concepts of justice and fairness, think about the difference between opinions and facts, question authority and rules critically, and consider what it means to be a good citizen.",
        "4": "In fourth grade, students think about free will and choices, explore concepts of truth and lying, discuss ethical dilemmas in age-appropriate contexts, question what makes something real, and consider different perspectives on moral issues.",
        "5": "In fifth grade, students explore philosophical questions about knowledge (how do we know things?), discuss concepts of equality and justice, think about the nature of happiness and good life, question assumptions in science and society, and consider ethical implications of technology.",
        "6": "In sixth grade philosophy (often in literature/social studies), students study ancient Greek philosophy basics (Socrates, Plato, Aristotle), explore questions about reality and appearance, discuss virtue ethics and what makes a good person, learn about logic and reasoning, and consider questions about existence and purpose.",
        "7": "In seventh grade, students may explore Eastern philosophy basics (Buddhism, Confucianism, Taoism), discuss concepts of self and consciousness, think about free will versus determinism, learn about different ethical systems, and question the nature of knowledge and truth.",
        "8": "In eighth grade, students explore Enlightenment philosophy and its influence, discuss social contract theory, think about individual rights versus collective good, learn about reasoning and logical fallacies, and consider philosophical questions in science.",
        "9": "In ninth grade (World History/Literature), students study Renaissance humanism, explore philosophical foundations of revolutions, discuss natural rights philosophy (Locke, Rousseau), learn about rationalism and empiricism, and consider questions about political philosophy and justice.",
        "10": "In tenth grade, students may study existentialism and questions of meaning, explore utilitarian and deontological ethics, discuss philosophy of mind and consciousness, learn about phenomenology and lived experience, and consider environmental philosophy and ethics.",
        "11": "In eleventh grade, students may study American pragmatism, explore feminist philosophy and critique of traditional philosophy, discuss postmodern philosophy and critique of grand narratives, learn about philosophy of science and scientific method, and consider contemporary ethical issues philosophically.",
        "12": "In twelfth grade philosophy (often elective), students study major philosophical traditions systematically, explore epistemology (theory of knowledge), discuss metaphysics and ontology, learn about philosophy of language and meaning, study ethics in depth (meta-ethics, normative ethics, applied ethics), and engage with contemporary philosophical debates."
    },
    "economics": {
        "K": "In kindergarten economics, students learn the difference between needs and wants, understand that people work to earn money, explore goods and services, learn about making choices when you can't have everything, and understand basic concepts of buying and selling.",
        "1": "In first grade economics, students learn about different jobs people do, understand that money can be saved or spent, explore how goods are produced, learn about scarcity (limited resources), and understand trading and exchange.",
        "2": "In second grade economics, students learn about producers and consumers, understand opportunity cost in simple terms, explore how businesses work, learn about different types of money (coins and bills), and understand specialization (people are good at different things).",
        "3": "In third grade economics, students learn about supply and demand basics, understand human capital (skills and knowledge), explore natural resources and their use, learn about markets and competition, and understand imports and exports in simple terms.",
        "4": "In fourth grade economics, students study their state's economy and resources, learn about factors of production (land, labor, capital), understand entrepreneurship, explore taxes and government services, and study regional economic specialization.",
        "5": "In fifth grade economics, students study the American economic system, learn about market economy versus command economy, understand banking and how it works, explore economic decisions made by individuals and government, and study how geography affects economic activities.",
        "6": "In sixth grade economics, students study economic systems around the world, learn about GDP and measuring economic activity, understand economic development and standards of living, explore international trade and globalization, and study currency and exchange rates.",
        "7": "In seventh grade economics, students learn about business organization (sole proprietorship, partnership, corporation), understand profit and loss, explore marketing and advertising, study labor markets and wages, and learn about economic growth and recession.",
        "8": "In eighth grade economics, students study economic aspects of American history, learn about banking system and Federal Reserve basics, understand fiscal policy and government spending, explore income distribution and economic inequality, and study stock market basics.",
        "9": "In ninth grade (integrated with World History), students study economic aspects of imperialism and globalization, learn about capitalism and socialism as economic systems, understand economic causes and effects of major historical events, explore development economics, and study international economic organizations (IMF, World Bank).",
        "10": "In tenth grade, students continue studying economic systems comparatively, learn about transition economies, understand economic aspects of globalization in depth, explore labor rights and working conditions globally, and study sustainable development from economic perspective.",
        "11": "In eleventh grade, students study American economic history, learn about major economic policies and their effects, understand business cycles and economic indicators, explore role of government in economy, and study contemporary economic issues (debt, deficit, trade policy).",
        "12": "In twelfth grade economics (often required course), students study microeconomics (supply and demand, elasticity, market structures, market failures), macroeconomics (GDP, inflation, unemployment, fiscal and monetary policy), understand financial literacy (banking, credit, investing, insurance), explore international economics and trade policy, and study contemporary economic issues and policy debates."
    },
    "law": {
        "K": "In kindergarten, law concepts begin with understanding classroom rules and why they exist, learning about fairness and taking turns, understanding consequences for actions, learning to resolve conflicts peacefully, and recognizing authority figures who help keep us safe (teachers, parents, police).",
        "1": "In first grade, students learn about school rules and their purposes, understand the concept of property and respecting others' belongings, learn about community helpers who enforce rules (police officers, crossing guards), discuss concepts of right and wrong, and understand basic safety rules and laws.",
        "2": "In second grade, students learn about rules at home, school, and community, understand that laws are rules for everyone in society, explore consequences of breaking rules, learn about judges and courts in simple terms, and discuss concepts of honesty and integrity.",
        "3": "In third grade, students learn about local government and laws, understand branches of government basics, explore rights and responsibilities of citizens, learn about voting and democracy, and study famous documents like the Constitution in simple terms.",
        "4": "In fourth grade, students study state government and laws, learn about how laws are made at state level, understand individual rights in their state constitution, explore historical laws and their effects, and learn about courts and legal system basics.",
        "5": "In fifth grade, students study the U.S. Constitution and Bill of Rights, learn about separation of powers and checks and balances, understand individual rights (freedom of speech, religion, etc.), explore how laws are made at federal level, and study landmark Supreme Court cases in simple terms.",
        "6": "In sixth grade, students learn about different legal systems around the world, understand rule of law and its importance, explore human rights and international law basics, study laws in ancient civilizations (Code of Hammurabi, Roman law), and learn about juvenile justice system.",
        "7": "In seventh grade, students study constitutional principles in more depth, learn about civil rights and civil liberties, understand criminal versus civil law, explore the court system structure (trial, appellate, supreme), and study how laws reflect and shape society.",
        "8": "In eighth grade, students study constitutional development in American history, learn about landmark Supreme Court cases and their impact, understand due process and equal protection, explore expansion of rights over time, and study how Constitution can be amended.",
        "9": "In ninth grade (World History), students study development of legal systems historically, learn about natural law and legal philosophy, understand international law and treaties, explore human rights law and violations, and study how legal systems differ across cultures.",
        "10": "In tenth grade, students may study comparative legal systems, learn about common law versus civil law traditions, understand international courts and tribunals, explore environmental law and regulation, and study how globalization affects legal systems.",
        "11": "In eleventh grade (U.S. History), students study constitutional issues throughout American history, learn about civil rights legislation and its evolution, understand federalism and state versus federal power, explore executive power and its limits, and study how Supreme Court interpretations have changed over time.",
        "12": "In twelfth grade (Government/Law elective), students study constitutional law in depth, learn about criminal law and criminal procedure, understand civil law including torts and contracts, explore administrative law and regulatory agencies, study current legal controversies and debates, and may participate in mock trials or moot court activities."
    }
}


def seed_domain(domain_name: str, service_api, grade_knowledge: dict) -> None:
    """
    Seed a single domain bank with grade level knowledge.

    Args:
        domain_name: Name of the domain (e.g., "math", "science")
        service_api: The service API function for the domain bank
        grade_knowledge: Dictionary mapping grade levels to knowledge content
    """
    print(f"\nSeeding {domain_name} domain bank...")

    grades = ["K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    stored_count = 0
    duplicate_count = 0

    for grade in grades:
        if grade in grade_knowledge:
            content = grade_knowledge[grade]

            fact = {
                "content": content,
                "confidence": 0.95,
                "verification_level": "established_fact",
                "source": "K-12 curriculum standards",
                "validated_by": "educational_standards",
                "metadata": {
                    "tier": "stm",
                    "grade_level": grade,
                    "domain": domain_name
                }
            }

            try:
                response = service_api({
                    "op": "STORE",
                    "payload": {"fact": fact}
                })

                if response.get("ok"):
                    # Response uses 'payload' key, not 'result'
                    result = response.get("payload", {})
                    if result.get("duplicate"):
                        duplicate_count += 1
                        print(f"  Grade {grade}: Already exists (duplicate)")
                    else:
                        stored_count += 1
                        print(f"  Grade {grade}: ✓ Stored")
                else:
                    error_info = response.get("error", {})
                    error_msg = error_info.get("message", str(error_info)) if isinstance(error_info, dict) else str(error_info)
                    print(f"  Grade {grade}: ✗ Error - {error_msg}")
            except Exception as e:
                print(f"  Grade {grade}: ✗ Exception - {str(e)}")
                import traceback
                traceback.print_exc()

    print(f"\n{domain_name} summary: {stored_count} new facts stored, {duplicate_count} duplicates skipped")

    # Rebuild index after seeding
    try:
        print(f"Rebuilding index for {domain_name}...")
        index_response = service_api({"op": "REBUILD_INDEX"})
        if index_response.get("ok"):
            records_indexed = index_response.get("payload", {}).get("records_indexed", 0)
            print(f"✓ Index rebuilt ({records_indexed} records indexed)")
        else:
            print(f"✗ Index rebuild failed")
    except Exception as e:
        print(f"✗ Index rebuild exception: {str(e)}")


def main():
    """Main function to seed all domain banks."""
    print("=" * 70)
    print("Seeding Domain Banks with Grade Level Knowledge (K-12)")
    print("=" * 70)

    domains = [
        ("math", math_api),
        ("science", science_api),
        ("history", history_api),
        ("technology", technology_api),
        ("arts", arts_api),
        ("language_arts", language_arts_api),
        ("geography", geography_api),
        ("philosophy", philosophy_api),
        ("economics", economics_api),
        ("law", law_api)
    ]

    total_stored = 0

    for domain_name, service_api in domains:
        if domain_name in GRADE_KNOWLEDGE:
            seed_domain(domain_name, service_api, GRADE_KNOWLEDGE[domain_name])
        else:
            print(f"\nSkipping {domain_name} - no grade knowledge defined")

    print("\n" + "=" * 70)
    print("Seeding complete!")
    print("=" * 70)

    # Print counts for each domain
    print("\nFinal record counts per domain:")
    for domain_name, service_api in domains:
        try:
            count_response = service_api({"op": "COUNT"})
            if count_response.get("ok"):
                counts = count_response.get("payload", {})
                stm = counts.get("stm", 0)
                mtm = counts.get("mtm", 0)
                ltm = counts.get("ltm", 0)
                total = stm + mtm + ltm
                print(f"  {domain_name:20s}: {total:3d} total (STM: {stm}, MTM: {mtm}, LTM: {ltm})")
        except Exception as e:
            print(f"  {domain_name:20s}: Error getting count - {str(e)}")


if __name__ == "__main__":
    main()
